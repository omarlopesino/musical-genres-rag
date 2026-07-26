from musical_genres_rag.Renderer import EntityRenderer
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI
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

class RagResponse:

    def __init__(self, query, response):
        # @todo include stats!
        self.query = query
        self.response = response

    def getResponse(self):
        return self.response

    def toJson(self):
        return json.dumps({
            "query": self.query,
            "response": self.response.output_parsed.model_dump()
        })

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

class Rag:

    def __init__(self, repository, index, responseClass):
        self.llm = OpenAI()
        self.repository = repository
        self.index = index
        self.responseClass = responseClass

    def query(self, query):
        results = self._queryIndex(query)
        entities = self.repository.loadMultiple(results)
        prompt = self._buildPrompt(query, entities)
        llm_response = self._queryLlm(prompt)
        return RagResponse(query, llm_response)

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
