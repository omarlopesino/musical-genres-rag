from pydantic import BaseModel, Field
from musical_genres_rag.Renderer import EntityRenderer
from typing import List, Literal
from openai import OpenAI
import pandas

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

import csv
import json

GROUND_TRUTH_PATH = './tests/ground_truth/ground_truth.csv'
ANSWERS_PATH = './tests/ground_truth/responses.json'

MODEL = 'gpt-5.4-mini'

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
    
    def __init__(self, repository, responseClass):
        self.repository = repository
        self.responseClass = responseClass
        self.llm = OpenAI()

    def generate(self, outputPath = GROUND_TRUTH_PATH):
        # @todo tqdm
        # @todo load all
        entities = self.repository.loadMultiple()
        ground_truth = []
        for entity in entities:
            entity_ground_truth = self._queryEntityGroundTruth(entity)
            for question in entity_ground_truth["questions"]:
                ground_truth.append(question)
        ground_truth_dataframe = pandas.DataFrame(ground_truth)
        ground_truth_dataframe.to_csv(outputPath, index = False)

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

    def __init__(self, repository):
        super().__init__(repository, GenreQuestions)

class GroundTruthAnswers:

    def __init__(self, rag, groundTruthPath = GROUND_TRUTH_PATH):
        self.rag = rag
        self.groundTruthPath = groundTruthPath

    def generate(self):
        with open(self.groundTruthPath, newline='') as csvfile:
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
        with open(ANSWERS_PATH, 'w') as jsonfile:
            json.dump(responses, jsonfile, indent = 2)


class EvaluationRunner:

    def __init__(self, index, groundTruthPath = GROUND_TRUTH_PATH):
        self.index = index
        self.groundTruthPath = groundTruthPath

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
        cases = []
        with open(self.groundTruthPath, newline='') as csvfile:
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

