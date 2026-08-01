
from musical_genres_rag.models import EntityModel

class Renderer():

    def __init__(self, entity):
        self.entity = entity

    """Asks the entity for its properties: vars() on a model would leak _state and drop the relations"""
    def _getProperties(self):
        return self.entity.getProperties()

    def render(self):
        pass

class TextRenderer(Renderer):

    def render(self):
        properties = self._getProperties()
        text = ''
        for property, value in properties.items():
            valueText = self.renderProperty(property, value)
            text = text + valueText + "\n"
        return text

    def renderProperty(self, property, value):
        if (isinstance(value, EntityModel)):
            renderer = TextRenderer(value)
            rendered = renderer.render()
            finalValue = property + ":\n" + rendered
        elif (isinstance(value, list)):
            finalValue = "\n".join([self.renderProperty(property + '#0', val) for val in value])
        else:
            finalValue = property + ':' + str(value)

        return finalValue

class JsonRenderer(Renderer):

    def render(self):
        properties = self._getProperties()
        jsonDict = dict()
        for property, value in properties.items():
            valueNormalized = self.renderProperty(property, value)
            jsonDict[property] = valueNormalized
        return jsonDict

    def renderProperty(self, property, value):
        if (isinstance(value, EntityModel)):
            renderer = JsonRenderer(value)
            rendered = renderer.render()
            finalValue = rendered
        elif (isinstance(value, list)):
            finalValue = [self.renderProperty(property + '#0', val) for val in value]
        else:
            finalValue = value

        return finalValue

"""The properties as prose, for a model that reads meaning rather than words.

Keys, the "#0" a list index leaves behind and ids are all noise once a document is pooled into one
vector, so none are emitted. Relations are named and not described: their descriptions dilute the
entity's own.
"""
class ProseRenderer(Renderer):

    """Never rendered: a surrogate key describes nothing"""
    SKIPPED = ('id',)

    def render(self):
        sentences = []
        relations = []
        for property, value in self._getProperties().items():
            if property in self.SKIPPED:
                continue

            if isinstance(value, list):
                if value:
                    relations.append(self.renderProperty(property, value))
            elif value is not None:
                sentences.append(str(value).strip().rstrip('.'))

        return ' '.join(['. '.join(sentences) + '.', *relations])

    """A relation as its names, under the property they belong to"""
    def renderProperty(self, property, value):
        return '{property}: {names}.'.format(
            property = property,
            names = ', '.join(str(one) for one in value),
        )

class EntityRenderer():
    def __init__(self, entity):
        self.entity = entity

    def render(self, mode = 'text'):
        match mode:
            case 'json':
                renderer = JsonRenderer(self.entity)

            case 'prose':
                renderer = ProseRenderer(self.entity)

            case 'text' | _:
                renderer = TextRenderer(self.entity)
        return renderer.render()
