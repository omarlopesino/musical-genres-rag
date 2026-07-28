from pydantic import BaseModel, Field
from musical_genres_rag.models import Attachment
from musical_genres_rag.Renderer import EntityRenderer
from typing import List, Literal
from datetime import datetime
from openai import OpenAI
import pandas

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

import csv
import json

GROUND_TRUTH_DIRECTORY = './tests/ground_truth'
TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'

MODEL = 'gpt-5.4-mini'

"""Every generated file carries the moment it was written, so runs never overwrite each other"""
def buildAttachmentPath(name, extension, directory = GROUND_TRUTH_DIRECTORY):
    return '{directory}/{name}_{timestamp}.{extension}'.format(
        directory = directory,
        name = name,
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT),
        extension = extension,
    )

"""The generators read whatever ground truth was registered last, so a run always scores the newest set"""
def requireLatestGroundTruth(attachmentsRepository):
    groundTruth = attachmentsRepository.getLatestGroundTruth()
    if groundTruth is None:
        raise RuntimeError('No ground truth registered, run "make groundtruth" first.')
    return groundTruth

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
                response = self.rag.query(question)
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


class EvaluationRunner:

    def __init__(self, index, attachmentsRepository):
        self.index = index
        self.attachmentsRepository = attachmentsRepository

    def execute(self):
        searchEvaluationResults = self._evaluateSearch()
        searchEvaluationResults.print()

    def _evaluateSearch(self):
        dataset = Dataset(
            name = 'musical_genres_rag',
            cases = self._generateAllCases(),
            evaluators = [HitRate(), MRR()]
        )

        return dataset.evaluate_sync(self.index.search)

    def _generateAllCases(self):
        groundTruth = requireLatestGroundTruth(self.attachmentsRepository)
        cases = []
        with open(groundTruth.getPath(), newline='') as csvfile:
            reader = csv.reader(csvfile)
            headings = next(reader)
            for index, row in enumerate(reader):
                cases.append(self._generateUseCase(row, index))
        return cases

    def _generateUseCase(self, row, index):
        id, genre, kind, question = row
        return Case(
            name = genre + '_' + kind + '_' + str(index),
            inputs = question,
            metadata = {
                'id': id,
                'kind': kind,
                'genre': genre,
                'question': question
            }
        )

"""Checks if the expected genre is retrieved at all. Averaged over cases it is the hit rate"""
class HitRate(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        return int(ctx.metadata['id']) in ctx.output

"""Reciprocal rank of the expected genre. Averaged over cases it is the MRR"""
class MRR(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        id = int(ctx.metadata['id'])
        if id not in ctx.output:
            return 0.0
        return 1 / (ctx.output.index(id) + 1)

"""Checks if the output contains the genre"""
class ContainsGenre(Evaluator):

    def evaluate(self, ctx: EvaluatorContext):
        return ctx.metadata.genre == ctx.output.getAnswer().genre

"""Checks if the output contains the genre"""
class Cost(Evaluator):
    def evaluate(self, ctx: EvaluatorContext):
        response = ctx.output.getResponse()
        input_cost = response.input_tokens / 1_000_000 * 0.6
        output_cost = response.output_tokens / 1_000_000 * 0.4
        return {
            'input_tokens': float(ctx.output.input_tokens),
            'output_tokens': float(ctx.output.output_tokens),
            'total_cost': input_cost + output_cost,
        }
        return ctx.metadata.genre == ctx.output.genre

