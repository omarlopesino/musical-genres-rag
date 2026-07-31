from musical_genres_rag.Renderer import EntityRenderer
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI
from time import perf_counter
import json

INSTRUCTIONS = '''
You are a music genre specialist. Your goal is to teach the user about the genres
related to their request.

Use the context to find relevant information and provide accurate answers. Don't use outside knowledge. If the
question's answer is not in the context, answer must be "I don't know.". Relate the
user's question to the content, even when the question is vague.

The structured output must be done in a register halfway between technical and colloquial.
'''

PROMPT = '''
QUESTION: {question}

CONTEXT:
{context}
'''.strip()

MODEL = 'gpt-5.4-mini'

# What the model charges, in dollars per million tokens. Writing costs six times reading, which is
# why a cost is worked out from the two counts and never from their sum.
INPUT_PRICE_PER_MILLION = 0.75
OUTPUT_PRICE_PER_MILLION = 4.50

"""What one call cost, in dollars, from what it read and what it wrote"""
def cost(input_tokens, output_tokens):
    return (input_tokens * INPUT_PRICE_PER_MILLION + output_tokens * OUTPUT_PRICE_PER_MILLION) / 1_000_000

"""What an answer reads like when the context does not hold it, whether the LLM said so or nothing was retrieved"""
UNKNOWN_ANSWER = "I don't know."

class RagResponse:

    def __init__(self, query, retrieved, response, duration, prompt = None):
        self.query = query
        self.retrieved = retrieved
        self.response = response
        self.duration = duration
        self.prompt = prompt

    def getResponse(self):
        return self.response

    """The context the answer was written from, kept so a judge scores the answer against what the
    LLM was actually given rather than against the index as it stands today"""
    def getPrompt(self):
        return self.prompt

    """The ids the index returned, so retrieval and generation are scored over the same run"""
    def getRetrieved(self):
        return self.retrieved

    def getAnswer(self):
        return self.response.output_parsed.model_dump()

    """Seconds the whole query took: the LLM response carries tokens but never the time they cost"""
    def getDuration(self):
        return self.duration

    def getInputTokens(self):
        return self.response.usage.input_tokens

    def getOutputTokens(self):
        return self.response.usage.output_tokens

    """What this call cost, priced as the model charges rather than stored beside the counts"""
    def getCost(self):
        return cost(self.getInputTokens(), self.getOutputTokens())

    """Which model wrote it, as the API resolved it rather than as the constant asked for it"""
    def getModel(self):
        return self.response.model

    def toDict(self):
        return {
            "query": self.query,
            "retrieved": self.getRetrieved(),
            "prompt": self.getPrompt(),
            "answer": self.getAnswer(),
            "duration": round(self.getDuration(), 3),
            "input_tokens": self.getInputTokens(),
            "output_tokens": self.getOutputTokens(),
        }

    def toJson(self):
        return json.dumps(self.toDict())

    def _renderEntity(self, entity):
        renderer = EntityRenderer(entity)
        return renderer.render('json')

class Instrument(BaseModel):
    name: str = Field(description = "Exact instrument name from context")
    description: str = Field(description = "2 sentences that describes the Instrument, replying to user's question. Use information from context")

class Genre(BaseModel):
    name: str = Field(description = "Exact genre name from context")
    description: str = Field(description = "2 sentences that describes the genre, replying to user's question. Use information from context. Do not mention instruments here.")

class GenresRagResponse(BaseModel):
    answer: str = Field(description = "2-4 sentences containing the answer to the user question based on the context.")
    genres: List[Genre] = Field(description = "List of found genres. At most 5, ranked by relevance to the question. Every genre must appear only once. Empty when answer is not in the context.")
    instruments: List[Instrument] = Field(description = "List of found instruments. At most 5, ranked by relevance to the question. Every instrument must appear only once. Empty when answer is not in the context.")

"""Raised instead of prompting an LLM with a context the index never filled"""
class EmptyRetrievalError(RuntimeError):

    def __init__(self, query, duration = 0.0):
        super().__init__('The index returned no results for "{query}", so the LLM was not queried.'.format(query = query))
        self.query = query
        self.duration = duration

    def getQuery(self):
        return self.query

    """The search still cost time, and it is the only time this query ever spent"""
    def getDuration(self):
        return self.duration

"""The answer given when nothing was retrieved.

Shaped exactly like a generated one so an unanswerable query is still a row in the
answers file and a case in the evaluation, rather than a hole in both.
"""
class EmptyRagResponse(RagResponse):

    def __init__(self, query, duration = 0.0):
        super().__init__(query, [], None, duration)

    def getAnswer(self):
        return GenresRagResponse(answer = UNKNOWN_ANSWER, genres = [], instruments = []).model_dump()

    def getInputTokens(self):
        return 0

    def getOutputTokens(self):
        return 0

    """No model wrote this one: nothing was retrieved, so nothing was asked of any of them"""
    def getModel(self):
        return None

class Rag:

    def __init__(self, repository, index, responseClass):
        self.llm = OpenAI()
        self.repository = repository
        self.index = index
        self.responseClass = responseClass

    def query(self, query):
        start = perf_counter()
        results = self._queryIndex(query)
        # No results means no context, and loadMultiple reads an empty selection as "load everything"
        if not results:
            raise EmptyRetrievalError(query, perf_counter() - start)
        entities = self.repository.loadMultiple(results)
        prompt = self._buildPrompt(query, entities)
        llm_response = self._queryLlm(prompt)
        return RagResponse(query, results, llm_response, perf_counter() - start, prompt)

    """Whoever holds a Rag never holds its index, so the engine it retrieved with is reachable from here"""
    def getEngineName(self):
        return self.index.getEngineName()

    def _queryIndex(self, query):
        return self.index.search(query)

    def _buildContext(self, entities):
        return "\n".join([self._renderEntity(entity) for entity in entities])
        
    def _renderEntity(self, entity):
        renderer = EntityRenderer(entity)
        return renderer.render()

    def _buildPrompt(self, query, entities):
        context = self._buildContext(entities)
        return PROMPT.format(
            question=query, context=context
        )

    def _queryLlm(self, prompt):
        input_messages = [
            {'role': 'developer', 'content': INSTRUCTIONS},
            {'role': 'user', 'content': prompt}
        ]

        response = self.llm.responses.parse(
            model=MODEL,
            input=input_messages,
            text_format=self.responseClass
        )

        return response

class GenresRag(Rag):

    def __init__(self, repository, index):
        super().__init__(repository, index, GenresRagResponse)
