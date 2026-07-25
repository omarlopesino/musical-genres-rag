
from musical_genres_rag.Model import BaseModel

class Renderer():

    def __init__(self, entity):
        self.entity = entity

    def _getProperties(self):
        return vars(self.entity)

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
        if (isinstance(value, BaseModel)):
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
        if (isinstance(value, BaseModel)):
            renderer = JsonRenderer(value)
            rendered = renderer.render()
            finalValue = rendered
        elif (isinstance(value, list)):
            finalValue = [self.renderProperty(property + '#0', val) for val in value]
        else:
            finalValue = value

        return finalValue

class EntityRenderer():
    def __init__(self, entity):
        self.entity = entity
    
    def render(self, mode = 'text'):
        match mode:
            case 'json':
                renderer = JsonRenderer(self.entity)

            case 'text' | _:
                renderer = TextRenderer(self.entity)
        return renderer.render()
