from musical_genres_rag.Progress import NULL_PROGRESS
from musical_genres_rag.Rag import MODEL
from pydantic import BaseModel, Field
from openai import OpenAI
import json

"""What a judge makes of an answer somebody already read.

The person who asked pressed a thumb, which says whether they were served and nothing about why.
This reads the same answer back against the very context it was written from — the feedback row
carries it — and writes down how well it answered and what was wrong with it where something was.

Both verdicts end up on one row, so the thumb and the judgement are read side by side. The thumb is
deliberately kept out of the prompt below: two verdicts are only worth comparing while neither of
them was told what the other said.
"""

INSTRUCTIONS = '''
You are judging how well an answer served the question it was given for.

You will be shown the question, the context the answer was written from, and the answer itself.

Judge only what is in front of you. An answer is relevant when it answers the question out of that
context; it is not when it answers something else, contradicts the context, or brings in knowledge
the context does not hold. "I don't know." is the right answer to a question the context does not
answer, and is judged as such rather than as a failure.
'''.strip()

PROMPT = '''
QUESTION: {question}

THE PROMPT IT WAS ANSWERED FROM:
{context}

WHAT WAS ANSWERED:
{answer}
'''.strip()

# Read by nothing that was retrieved, which is an answer of its own and not a hole in the prompt
NO_CONTEXT = 'Nothing was retrieved, so the answer was written from no context at all.'

"""What a run is spending its time on, for whoever is following it"""
JUDGING = 'judging'

# How many answers one run reads at most. Every one of them is a paid call, so a run is bounded by
# what it may spend rather than by how much feedback happens to have piled up; the oldest go first,
# and whatever is left over waits for the next run.
DEFAULT_LIMIT = 100

class JudgeResult(BaseModel):
    relevance: float = Field(description = "How well the answer served the question, between 0 for an answer that did not serve it at all and 1 for one that answered it fully out of the context.")
    judgement: str = Field(description = "1-2 sentences saying why that relevance was given, naming what the answer got right or wrong.")

"""Scores the answers people left feedback on, one LLM call each.

Reads what nobody has judged yet, so a run judges each answer once however often it is run.
"""
class FeedbackRelevanceJudge:

    def __init__(self, repository, batchRepository, llm = None):
        self.repository = repository
        self.batchRepository = batchRepository
        # Built here unless it is handed one, so nothing has to open a client to build a judge
        self.llm = llm if llm is not None else OpenAI()

    """Judges the oldest answers pending, and returns the run they were judged under and how many
    of them there were.

    The batch is opened only once there is something to put in it, so a run that finds nothing
    pending costs nothing and leaves no empty run behind to link to.
    """
    def score(self, progress = NULL_PROGRESS, limit = DEFAULT_LIMIT):
        feedbacks = self.getFeedbacksWithoutJudge(limit)
        progress.start(JUDGING, len(feedbacks))
        if not feedbacks:
            return [None, 0]

        batch = self.batchRepository.create()
        for feedback in feedbacks:
            self.judge(feedback, batch)
            progress.advance()

        return [batch, len(feedbacks)]

    def getFeedbacksWithoutJudge(self, limit = DEFAULT_LIMIT):
        return self.repository.findWithoutJudgement(limit)

    """What the answer was asked, what it was given and what it made of it.

    The stored prompt is the whole of what the LLM was handed, the question included, so the
    question above it is read as the first thing it was told and not as a second one.

    The answer is the whole stored response rather than its prose alone, so the genres and
    instruments it named are judged along with the sentences that introduced them.
    """
    def buildPrompt(self, feedback):
        conversation = feedback.getConversation()
        answer = conversation.getAnswer()

        return PROMPT.format(
            question = conversation.getQuestion(),
            context = answer['prompt'] if answer['prompt'] else NO_CONTEXT,
            answer = json.dumps(answer['answer']),
        )

    """The verdict on one answer, written onto the row it was read from, under the run that read it"""
    def judge(self, feedback, batch):
        prompt = self.buildPrompt(feedback)
        input_messages = [
            {'role': 'developer', 'content': INSTRUCTIONS},
            {'role': 'user', 'content': prompt}
        ]

        response = self.llm.responses.parse(
            model=MODEL,
            input=input_messages,
            text_format=JudgeResult
        )

        result = response.output_parsed
        feedback.judgement = result.judgement
        feedback.relevance = result.relevance
        feedback.judge_batch = batch

        return self.repository.saveJudgement(feedback)
