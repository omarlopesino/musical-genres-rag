from pydantic import BaseModel, Field
from musical_genres_rag.Renderer import EntityRenderer
from typing import List, Literal
from openai import OpenAI
from pandas import DataFrame

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

    def generate(self, outputPath = './tests/ground_truth/ground_truth.csv'):
        # @todo tqdm
        # @todo load all
        entities = self.repository.loadMultiple()
        ground_truth = []
        for entity in entities:
            entity_ground_truth = self._queryEntityGroundTruth(entity)
            for question in entity_ground_truth["questions"]:
                ground_truth.append(question)
        ground_truth_dataframe = DataFrame(ground_truth)
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

class EvaluationRunner:
    pass
