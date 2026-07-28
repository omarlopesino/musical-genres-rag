from pydantic import BaseModel, Field
from musical_genres_rag.models import Attachment, EvaluationRun
from musical_genres_rag.Rag import EmptyRagResponse, EmptyRetrievalError, UNKNOWN_ANSWER
from musical_genres_rag.Renderer import EntityRenderer
from typing import List, Literal
from datetime import datetime
from openai import OpenAI
import pandas

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.reporting import EvaluationReportAdapter

import csv
import json

GROUND_TRUTH_DIRECTORY = './tests/ground_truth'
TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'

"""The only two columns every ground truth must carry: what was asked, and what it was asked about"""
QUESTION_COLUMN = 'question'
ID_COLUMN = 'id'
# Everything else describes the subject, and is what a case is named after
RESERVED_COLUMNS = (ID_COLUMN, QUESTION_COLUMN)

MODEL = 'gpt-5.4-mini'

"""Every generated file carries the moment it was written, so runs never overwrite each other"""
def buildAttachmentPath(name, extension, directory = GROUND_TRUTH_DIRECTORY):
    return '{directory}/{name}_{timestamp}.{extension}'.format(
        directory = directory,
        name = name,
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT),
        extension = extension,
    )

"""Get the latest ground truth file genrated, if exists"""
def requireLatestGroundTruth(attachmentsRepository):
    groundTruth = attachmentsRepository.getLatestGroundTruth()
    if groundTruth is None:
        raise RuntimeError('No ground truth registered, run "make groundtruth" first.')
    return groundTruth

"""Get the latest ground truth answers file generated, if exists."""
def requireLatestGroundTruthAnswer(attachmentsRepository, index):
    latestResponse = attachmentsRepository.getLatestGroundTruthResponses(index.getEngineName())
    # Answers belong to the engine that produced them, so a new engine has none until it is run
    if latestResponse is None:
        raise RuntimeError('No ground truth answers registered for "{engine}", run "make createAnswers ENGINE={engine}" first.'.format(
            engine = index.getEngineName(),
        ))
    return latestResponse

INSTRUCTIONS = '''
You are some musician looking up to learn about genres. 

You will receive a full genre as the context.

You don't know this genre's name — you are trying to find it. Type into a
search engine the 5 things you would actually search to track it down,
based on what the context tells you about it.

Rules:
- Genre name must not be contained in the question.
- Ask what the genre context actually answers.
'''.strip()

PROMPT = '''
GENRE:
{genre}
'''.strip()

class GenreQuestion(BaseModel):
    id: str = Field(description = "Exact genre ID from context")
    genre: str = Field(description = "The exact name of the genre from context.")
    kind: Literal['vibe', 'instruments', 'related_genres'] = Field(description = "The trait the question uses to describe the genre.")
    question: str = Field(description = "A 10-15 word question about the genre, without naming it.")

class GenreQuestions(BaseModel):
    questions : List[GenreQuestion] = Field(description = "List of 5 questions.")

class GroundTruth:
    
    def __init__(self, repository, attachmentsRepository, responseClass):
        self.repository = repository
        self.attachmentsRepository = attachmentsRepository
        self.responseClass = responseClass
        self.llm = OpenAI()

    """Returns the attachment the questions were written to"""
    def generate(self, outputPath = None):
        # @todo tqdm
        # @todo load all
        outputPath = outputPath if outputPath is not None else buildAttachmentPath('ground_truth', 'csv')
        entities = self.repository.loadMultiple()
        ground_truth = []
        for entity in entities:
            entity_ground_truth = self._queryEntityGroundTruth(entity)
            for question in entity_ground_truth["questions"]:
                ground_truth.append(question)
        ground_truth_dataframe = pandas.DataFrame(ground_truth)
        ground_truth_dataframe.to_csv(outputPath, index = False)

        # No engine: the questions come straight from the repository, no index is searched
        return self.attachmentsRepository.create(outputPath, Attachment.Type.GROUND_TRUTH)

    def _queryEntityGroundTruth(self, entity):
        prompt = PROMPT.format(genre = self._renderEntity(entity))
        input_messages = [
            {'role': 'developer', 'content': INSTRUCTIONS},
            {'role': 'user', 'content': prompt}
        ]

        response = self.llm.responses.parse(
            model=MODEL,
            input=input_messages,
            text_format=self.responseClass
        )

        return response.output_parsed.model_dump()

    def _renderEntity(self, entity):
        renderer = EntityRenderer(entity)
        return renderer.render()

class GenreQuestionsGroundTruth(GroundTruth):

    def __init__(self, repository, attachmentsRepository):
        super().__init__(repository, attachmentsRepository, GenreQuestions)

class GroundTruthAnswers:

    def __init__(self, rag, attachmentsRepository):
        self.rag = rag
        self.attachmentsRepository = attachmentsRepository

    """Returns the attachment the answers were written to"""
    def generate(self):
        groundTruth = requireLatestGroundTruth(self.attachmentsRepository)
        outputPath = buildAttachmentPath('ground_truth_answers', 'json')
        with open(groundTruth.getPath(), newline='') as csvfile:
            reader = csv.reader(csvfile)
            headings = next(reader)
            responses = []
            for row in reader:
                [id, genre, kind, question] = row
                response = self._answer(question)
                responses.append({
                    'id': id,
                    'kind': kind,
                    'genre': genre,
                    **response.toDict(),
                })
        with open(outputPath, 'w') as jsonfile:
            json.dump(responses, jsonfile, indent = 2)

        return self.attachmentsRepository.create(
            outputPath,
            Attachment.Type.GROUND_TRUTH_ANSWERS,
            self.rag.getEngineName(),
        )

    """A question the index cannot answer is still a question the evaluation must score, so it is
    recorded as an unanswered one rather than aborting a run of paid calls"""
    def _answer(self, question):
        try:
            return self.rag.query(question)
        except EmptyRetrievalError as error:
            return EmptyRagResponse(error.getQuery(), error.getDuration())


"""Scores a ground truth and stores what it scored.

Holds no knowledge of what the questions are about: the ground truth file names its own
columns, and a subclass names the response to score and the metrics worth running over it.
"""
class EvaluationRunner:

    def __init__(self, index, attachmentsRepository, evaluationRunsRepository, type, name, evaluators):
        self.index = index
        self.attachmentsRepository = attachmentsRepository
        self.evaluationRunsRepository = evaluationRunsRepository
        self.type = type
        self.name = name
        self.evaluators = evaluators
        # Resolved once, so the run is stored against the very file it scored
        self.groundTruth = requireLatestGroundTruth(attachmentsRepository)

    """Returns the stored run, printed as it is written so a failed save still shows the report"""
    def execute(self):
        report = self._evaluate()
        report.print()
        return self._save(report)

    """What a case is scored against: a subclass either replays a recorded run or queries live"""
    def _getResponse(self, question):
        raise NotImplementedError

    """The answers file a run scored, for the runs that scored one at all"""
    def _getGroundTruthAnswers(self):
        return None

    def _save(self, report):
        return self.evaluationRunsRepository.create(
            type = self.type,
            groundTruth = self.groundTruth,
            groundTruthAnswers = self._getGroundTruthAnswers(),
            retriever = self.index.getEngineName(),
            k = self.index.getLimit(),
            embeddingModel = self.index.getEmbeddingModel(),
            hitRate = self._averageAssertion(report, 'HitRate'),
            mrr = self._averageScore(report, 'MRR'),
            report = EvaluationReportAdapter.dump_python(report, mode = 'json'),
        )

    """A boolean evaluator lands in the assertions, which aggregate as one rate over every evaluator"""
    def _averageAssertion(self, report, name):
        values = [
            case.assertions[name].value for case in report.cases
                if name in case.assertions
        ]
        return sum(values) / len(values) if values else None

    def _averageScore(self, report, name):
        averages = report.averages()
        return averages.scores.get(name) if averages is not None else None

    def _evaluate(self):
        dataset = Dataset(
            name = self.name,
            cases = self._generateAllCases(),
            evaluators = self.evaluators,
        )

        return dataset.evaluate_sync(self._getResponse)

    def _generateAllCases(self):
        cases = []
        with open(self.groundTruth.getPath(), newline='') as csvfile:
            reader = csv.reader(csvfile)
            headings = next(reader)
            for index, row in enumerate(reader):
                cases.append(self._generateUseCase(headings, row, index))
        return cases

    """Every column becomes metadata, so a ground truth may carry traits this class never heard of"""
    def _generateUseCase(self, headings, row, index):
        metadata = dict(zip(headings, row))
        return Case(
            name = self._generateCaseName(metadata, index),
            inputs = metadata[QUESTION_COLUMN],
            metadata = metadata,
        )

    """Named after whatever traits the ground truth describes its subject by, never after the subject"""
    def _generateCaseName(self, metadata, index):
        traits = [
            value for heading, value in metadata.items()
                if heading not in RESERVED_COLUMNS
        ]
        return '_'.join([*traits, str(index)])

"""Scores the whole pipeline over a recorded run: what the index retrieved, and what the LLM made of it.

Replays the answers file rather than querying anything, so the generation it scores is
paid for once, by "make createAnswers".
"""
class GenresRagEvaluationRunner(EvaluationRunner):

    def __init__(self, index, attachmentsRepository, evaluationRunsRepository):
        super().__init__(
            index,
            attachmentsRepository,
            evaluationRunsRepository,
            EvaluationRun.Type.RAG,
            'musical_genres_rag',
            [
                HitRate(),
                MRR(),
                Cost(),
                GenreRagResponseHit(),
                ResponseGenerationTime(),
                HitDbRag(),
                GenreRagGenreHit(),
                GenreRagGenreMrr(),
            ],
        )
        self.groundTruthAnswers = requireLatestGroundTruthAnswer(attachmentsRepository, index)
        self.recordedResponses = self._loadRecordedResponses()

    def _getGroundTruthAnswers(self):
        return self.groundTruthAnswers

    def _getResponse(self, question):
        return next(
            response for response in self.recordedResponses
                if response['query'] == question
        )

    def _loadRecordedResponses(self):
        with open(self.groundTruthAnswers.getPath()) as file:
            return json.load(file)

"""Scores retrieval alone, by querying the index live.

Costs no LLM call and needs no answers file, so an engine, a mode or a k can be measured
as often as it is changed rather than only where generation was already paid for.
"""
class GenresRetrievalEvaluationRunner(EvaluationRunner):

    def __init__(self, index, attachmentsRepository, evaluationRunsRepository):
        super().__init__(
            index,
            attachmentsRepository,
            evaluationRunsRepository,
            EvaluationRun.Type.RETRIEVAL,
            'musical_genres_retrieval',
            [
                HitRate(),
                MRR(),
            ],
        )

    """Shaped like the retrieval half of a recorded response, so both runners share their evaluators"""
    def _getResponse(self, question):
        return {'retrieved': self.index.search(question)}

"""Checks if the expected genre is retrieved at all. Averaged over cases it is the hit rate"""
class HitRate(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        return int(ctx.metadata['id']) in ctx.output['retrieved']

"""Reciprocal rank of the expected genre. Averaged over cases it is the MRR"""
class MRR(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        id = int(ctx.metadata['id'])
        retrieved = ctx.output['retrieved']
        if id not in retrieved:
            return 0.0
        return 1 / (retrieved.index(id) + 1)

"""Checks if the output contains the genre"""
class GenreRagResponseHit(Evaluator):
    def evaluate(self, ctx: EvaluatorContext):
        response = ctx.output
        return response['answer']['answer'] != UNKNOWN_ANSWER

"""Checks if the output contains the genre"""
class ResponseGenerationTime(Evaluator):
    def evaluate(self, ctx: EvaluatorContext):
        response = ctx.output
        return response['duration']

"""Checks if the output contains the genre"""
class Cost(Evaluator):
    def evaluate(self, ctx: EvaluatorContext):
        response = ctx.output
        input_cost = response['input_tokens'] / 1_000_000 * 0.6
        output_cost = response['output_tokens'] / 1_000_000 * 0.4
        return {
            'input_tokens': float(ctx.output['input_tokens']),
            'output_tokens': float(ctx.output['output_tokens']),
            'total_cost': input_cost + output_cost,
        }

"""Retrieval and generation fail independently, so the pair is what tells them apart"""
class HitDbRag(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        retrieved = HitRate().evaluate(ctx)
        answered = GenreRagResponseHit().evaluate(ctx)
        if retrieved and answered:
            return 'answered'
        if retrieved:
            return 'generation_miss'
        if answered:
            return 'answered_without_genre'
        return 'retrieval_miss'

"""The genres an answer named, in the order it ranked them"""
def answeredGenres(output):
    return [normalizeGenre(genre['name']) for genre in output['answer']['genres']]

"""Names are matched as the ground truth and the answer both spell them, not byte for byte"""
def normalizeGenre(name):
    return name.strip().casefold()

"""Checks if the expected genre is named in the answer at all. Averaged over cases it is the hit rate"""
class GenreRagGenreHit(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        return normalizeGenre(ctx.metadata['genre']) in answeredGenres(ctx.output)

"""Reciprocal rank of the expected genre inside the answer. Averaged over cases it is the MRR"""
class GenreRagGenreMrr(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        genre = normalizeGenre(ctx.metadata['genre'])
        genres = answeredGenres(ctx.output)
        if genre not in genres:
            return 0.0
        return 1 / (genres.index(genre) + 1)
