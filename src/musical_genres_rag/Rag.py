from musical_genres_rag.Renderer import EntityRenderer
from openai import OpenAI
import json

INSTRUCTIONS = '''
You are a music genre specialist. Your goal is to teach the user about the genres
related to their request. Your answer must include the genres found and their
musical instruments.

Use the context to find relevant information and provide accurate answers. If the
answer is not in the context, respond with "I don't know." Always try to relate the
user's question to the content, even when the question is vague.

Write a detailed answer explaining the genres you found. Use prose,
in a register halfway between technical and colloquial. Open with a paragraph of
conclusions, then cover the genres one by one. Finally, describe the instruments you have found and why they match.

Format the answer as Markdown. Do not ask follow-up questions; the response is final.
'''

PROMPT = '''
QUESTION: {question}

CONTEXT:
{context}
'''.strip()

MODEL = 'gpt-5.4-mini'

class RagResponse:

    def __init__(self, query, response, entities):
        # @todo receive a wrapped response class to render a json
        # with only the response.
        self.query = query
        self.response = response
        self.entities = entities

    def getResponse(self):
        return self.response

    def toJson(self):
        pass

    def _renderEntity(self, entity):
        renderer = EntityRenderer(entity)
        return renderer.render('json')

class GenresRagResponse(RagResponse):

    def toJson(self):
        dataDict = {
            'response': self.response,
            'genres': [self._renderEntity(entity) for entity in self.entities],
            'instruments': [self._renderEntity(entity) for entity in self._getInstrumentsFromGenres(self.entities)]
        }
        return json.dumps(dataDict)

    def _getInstrumentsFromGenres(self, genres):
        instruments = {}
        for genre in genres:
            for instrument in genre.getInstruments():
                instruments[str(instrument.getId())] = instrument
        return instruments.values()

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
        return self.responseClass(query, llm_response, entities)

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

        response = self.llm.responses.create(
            model=MODEL,
            input=input_messages
        )

        return response

class GenresRag(Rag):

    def __init__(self, repository, index):
        super().__init__(repository, index, GenresRagResponse)
