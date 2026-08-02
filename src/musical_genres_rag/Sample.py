from pathlib import Path

from django.conf import settings

from musical_genres_rag.Demo import DEMO_DIRECTORY
from musical_genres_rag.Evaluation import RESPONSES_KEY
from musical_genres_rag.Progress import NULL_PROGRESS
from musical_genres_rag.Rag import cost, MODEL

import json
import random
import time

"""Traffic the dashboard can be watched moving, made without anybody asking anything.

Grafana draws eleven panels over the conversations people have had and what they made of the
answers, and both tables only fill up when somebody sits in the chat spending a call per question.
So on a clone it draws eleven empty panels, and even where it has been used it holds a handful of
questions a day: nothing that shows how a graph moves.

The material is already committed. The answers exported with the demo are fifty real questions and
the answers they got, each carrying the prompt it was written from, what it retrieved, how long it
took and what it read and wrote. Replaying those as conversations costs nothing and reads, panel by
panel, exactly like the traffic they came from.

Spread over a window rather than written at once, because rows sharing an instant draw no line. And
rated only some of the time, because not everybody presses a thumb, and a dashboard where every
answer was rated is not the one this project has.
"""

# Written into every sampled answer. Grafana reads answer->'answer'->>'answer' and nothing else, so
# this is invisible to all of it and still tells a sampled conversation from one somebody had.
SAMPLED_KEY = 'sampled'

# What a run is spending its time on, for whoever is following it
SAMPLING = 'sampling'

DEFAULT_SECONDS = 30
DEFAULT_CONVERSATIONS = 20
# Out of a hundred. The rest are answers nobody rated, which is most of them in any real week.
DEFAULT_FEEDBACK = 60

ANSWERS_PATTERN = 'ground_truth_answers_*.json'

MISSING_ANSWERS = 'No answers are committed at "{path}", so there is nothing to replay as traffic.'

"""How a thumb and a score are drawn together.

A rating is one person's verdict, so the two halves of it agree: somebody who pressed a thumb down
did not also score the answer as having served them. Drawn from these rather than independently,
so the relevance pie and the thumbs pie tell the same story.
"""
THUMB_UP = 1.0
THUMB_DOWN = 0.0
POSITIVE_SHARE = 75
RELEVANCE_UP = (0.72, 0.99)
RELEVANCE_DOWN = (0.05, 0.38)

"""What the judging of one answer reads and writes, as the real judge's calls have.

Smaller than answering: a judge is shown one question, one context and one answer, and replies with
a sentence and a number.
"""
JUDGE_INPUT_TOKENS = (400, 1200)
JUDGE_OUTPUT_TOKENS = (50, 150)

"""What a judge said, as one of these. Fabricated like the score beside it, and picked to match the
verdict rather than at random, so a row does not praise an answer it scored at nothing."""
JUDGEMENTS_UP = [
    'The answer names the genre the question asked about and describes it out of the context it was given.',
    'Answered fully from the context, naming the genre and the instruments the passage attributes to it.',
    'The question is answered directly, and everything it claims is in the context it was written from.',
]
JUDGEMENTS_DOWN = [
    'The answer names a genre the context does not attribute to the question, and brings in claims the passage does not hold.',
    'It answers something adjacent to what was asked, and the genres it lists are not the ones the context names.',
    'Little of this comes from the context: the question is left effectively unanswered.',
]

"""One replayed answer, wearing the face of a real one.

Not a subclass of RagResponse: it holds a call that was made somewhere else rather than one it made
itself, and there is no response object under it to read a usage or a model off. What it does have
is what a conversation is written from, which is why it is these methods and no others.
"""
class SampledResponse:

    def __init__(self, entry, model = MODEL):
        self.entry = entry
        self.model = model

    """The answer as it is stored, marked as replayed and without the case columns the file carries
    for the evaluation's sake: what is written down is a conversation, not a scored case"""
    def toDict(self):
        return {
            'query': self.entry['query'],
            'retrieved': self.entry['retrieved'],
            'prompt': self.entry['prompt'],
            'answer': self.entry['answer'],
            'duration': self.entry['duration'],
            'input_tokens': self.getInputTokens(),
            'output_tokens': self.getOutputTokens(),
            SAMPLED_KEY: True,
        }

    def getQuestion(self):
        return self.entry['query']

    def getDuration(self):
        return self.entry['duration']

    def getInputTokens(self):
        return self.entry['input_tokens']

    def getOutputTokens(self):
        return self.entry['output_tokens']

    """Priced by the very function a real call is priced by, so what the dashboard sums is one thing
    and not two that drifted apart"""
    def getCost(self):
        return cost(self.getInputTokens(), self.getOutputTokens())

    def getModel(self):
        return self.model

"""Writes that traffic, one conversation at a time, over a window of real seconds.

Real seconds on purpose: a row dates itself the moment it is inserted, so writing them as they are
meant to have arrived is what gives them the distinct timestamps a series is drawn from, and nothing
has to be backdated afterwards.
"""
class TrafficSampler:

    def __init__(self, conversationsRepository, feedbackRepository, judgeBatchRepository, directory = DEMO_DIRECTORY):
        self.conversationsRepository = conversationsRepository
        self.feedbackRepository = feedbackRepository
        self.judgeBatchRepository = judgeBatchRepository
        self.directory = directory

    """Returns the batch the ratings were opened under, how many conversations were written and how
    many of them somebody rated"""
    def sample(self, progress = NULL_PROGRESS, seconds = DEFAULT_SECONDS, conversations = DEFAULT_CONVERSATIONS, feedback = DEFAULT_FEEDBACK):
        entries = self._read()
        batch = self.judgeBatchRepository.create()
        interval = seconds / conversations

        progress.start(SAMPLING, conversations)

        rated = 0
        for written in range(conversations):
            response = SampledResponse(random.choice(entries))
            conversation = self.conversationsRepository.create(response.getQuestion(), response)

            if random.randrange(100) < feedback:
                self._rate(conversation, batch)
                rated = rated + 1

            progress.advance()

            # Not after the last one: the window is what the traffic is spread over, and waiting
            # past the end of it only makes the run outlast what it wrote
            if written < conversations - 1:
                time.sleep(interval)

        return [batch, conversations, rated]

    """One person's verdict, written as the two halves it really is.

    The thumb goes down through the same method the chat writes one with, and what a judge made of
    the same answer is written over it through the same one the judge writes with. Fabricated, both
    of them: a judgement is stored, which is exactly what keeps the feedback judge from reading this
    row back and paying to score it again.
    """
    def _rate(self, conversation, batch):
        positive = random.randrange(100) < POSITIVE_SHARE
        rating = self.feedbackRepository.save(conversation, THUMB_UP if positive else THUMB_DOWN)

        rating.judgement = random.choice(JUDGEMENTS_UP if positive else JUDGEMENTS_DOWN)
        rating.relevance = round(random.uniform(*(RELEVANCE_UP if positive else RELEVANCE_DOWN)), 2)
        rating.input_tokens = random.randint(*JUDGE_INPUT_TOKENS)
        rating.output_tokens = random.randint(*JUDGE_OUTPUT_TOKENS)
        rating.cost = cost(rating.input_tokens, rating.output_tokens)
        rating.judge_batch = batch

        return self.feedbackRepository.saveJudgement(rating)

    """The committed answers, read from the demo rather than from the database.

    Whatever is in ./data/demo is in every clone of this, so traffic is sampled whether or not
    anybody has loaded the demo or run the pipeline that would write a newer file.
    """
    def _read(self):
        directory = Path(settings.BASE_DIR, self.directory)
        files = sorted(directory.glob(ANSWERS_PATTERN))
        if not files:
            raise RuntimeError(MISSING_ANSWERS.format(path = directory))

        with files[-1].open(encoding = 'utf-8') as file:
            return json.load(file)[RESPONSES_KEY]
