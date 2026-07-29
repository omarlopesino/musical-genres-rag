#!/usr/bin/env python
import os

import django

# Django has to be configured before anything that reaches the ORM is imported, exactly as manage.py
# does it. uv installs src/ as an editable package, so there is no path juggling to do here either.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import altair
import pandas
import streamlit as st

from musical_genres_rag.models import Feedback
from musical_genres_rag.Rag import EmptyRagResponse, EmptyRetrievalError
from musical_genres_rag.services import buildEvaluationRunsRepository, buildFeedbackRepository, buildGenresRag

# Streamlit renders every bare expression a script leaves at module level, a docstring above a
# function included, so everything explanatory in this file is a comment instead.

# A report is reached by its own URL rather than by a click, so an Airflow task can link the run it
# just finished. The page the app navigates to and the page Airflow links are the same one.
REPORT_PATH = '/report'

# The chat is what the app opens on, so the evaluations moved off "/" and are linked back to by name
EVALUATIONS_PATH = '/evaluations'

# What a question may be, kept at the width of the column it is stored in so the box refuses
# what Postgres would have rejected on the way in
QUESTION_LENGTH = 255

# What survives a rerun. Every button press runs this script again from the top, so the answer on
# screen and the conversation it belongs to are held here rather than rebuilt.
ANSWER_STATE = 'answer'
CONVERSATION_STATE = 'conversation'
# The thumbs are their own widget per conversation, and this is what was last stored from them
THUMBS_STATE = 'thumbs-{conversation}'
SCORED_STATE = 'scored'

# st.feedback hands back the position of the thumb pressed, and this is what it is stored as
SCORES = {1: 1.0, 0: 0.0}

QUESTION_FORM = 'question'

SEARCHING = 'Searching the genres and writing an answer...'
FEEDBACK_THANKS = 'Thanks. Your feedback was stored.'
EMPTY_QUESTION = 'Write a question first.'
# Read with the field it stands in for: "The answer named no instruments."
EMPTY_NAMED = 'The answer named no {named}.'

# The two lists an answer carries, under the heading each is offered by
ANSWERED = {
    'genres': 'Genres',
    'instruments': 'Instruments',
}

# The label a rag run stores its outcome breakdown under. Retrieval runs never score it
OUTCOME_LABEL = 'HitDbRag'

# Every section of the report under the anchor its heading is given. The contents at the top and the
# headings below are both written from here, so a renamed section can never leave a link behind.
OUTCOMES = 'Outcomes'
FOUND = 'How often the genre was found'
REPORT_SECTION = 'Full Report'
SECTIONS = {
    OUTCOMES: 'outcomes',
    FOUND: 'found',
    REPORT_SECTION: 'report',
}

# The score holding the seconds a case took to answer. Only a run that generates an answer has one
GENERATION_TIME_SCORE = 'ResponseGenerationTime'

# Where an evaluator lands in a case. Each serializes six fields of which only the value is a result
EVALUATOR_GROUPS = ('assertions.', 'scores.', 'labels.')

# Left out of the cases table: pydantic-evals bookkeeping, and the copies metadata keeps of what
# output already says.
CASE_NOISE = [
    'inputs',
    'span_id',
    'trace_id',
    'expected_output',
    'source_case_name',
    'evaluator_failures',
    'name',
    'task_duration',
    'total_duration',
    'metadata.id',
    'metadata.kind',
    'metadata.genre',
    'output.id',
    'output.kind',
    'output.query',
    'output.retrieved',
    # Thousands of characters of rendered context. It is stored for a judge to read, not for a cell
    'output.prompt',
]

# Scored, and kept out of the table. The outcome is what the donut is drawn from, and the rest score
# numbers the output already carries: the generation time is "seconds", and Cost re-reports the two
# token counts as floats on its way to the only figure it works out for itself, the cost.
HIDDEN_EVALUATORS = [
    'HitDbRag',
    'GenreRagResponseHit',
    'ResponseGenerationTime',
    'input_tokens',
    'output_tokens',
    # Only ever 1 where the genre was named and 0 where it was not, which the gauges already say
    'GenreRagGenreMrr',
    # The two the gauges are drawn from. Whether the genre was retrieved is read off the expected
    # genre against the answer, so the column repeated what the row already showed.
    'HitRate',
    'GenreRagGenreHit',
]

# Where a rate is kept once the evaluation has worked it out for each boolean evaluator on its own
ASSERTION_RATES = 'assertion_rates'

# The evaluators worth a gauge, under the heading each is drawn with. Both answer the same question
# at a different point of the pipeline, so neither is named after the metric behind it. The heading
# is the label under its column, so it is short enough to sit there.
FOUND_CHARTS = {
    'HitRate': 'By the search',
    'GenreRagGenreHit': 'In the answer',
}

FOUND_LABEL = 'found'
FOUND_COLOUR = '#4c78a8'
# The rest of the hundred per cent, drawn as the track the fill is read against
MISSING_COLOUR = '#e6e4e2'
GAUGE_WIDTH = 56

# The answer names each genre and instrument with a description attached. Only the names fit a cell
NAMED_COLUMNS = ['output.answer.genres', 'output.answer.instruments']

# What a case asked, what came back and what the judge made of it lead the table, side by side,
# whatever order the report serialized its fields in.
LEADING_COLUMNS = ['metadata.question', 'output.answer.answer', 'LLMJudge', 'LLMJudge reason']

# The judge is the only evaluator that explains itself, and the explanation is the point of it
REASONED_EVALUATORS = ['LLMJudge']

# Held narrow, or the long prose takes the width from everything the case scored
NARROW_COLUMNS = ['metadata.question', 'output.answer.answer', 'LLMJudge reason']

# Edit these to change the headings the tables show. A column missing from the dict keeps its own name.
RUN_LABELS = {
    'id': 'id',
    'created_at': 'date',
    'type': 'type',
    'retriever': 'retriever',
    'report': 'report',
}

CASE_LABELS = {
    'metadata.question': 'question',
    'output.genre': 'expected genre',
    'output.query': 'query',
    'output.answer.answer': 'answer',
    'output.answer.genres': 'answered genres',
    'output.answer.instruments': 'answered instruments',
    'output.duration': 'seconds',
    'output.input_tokens': 'input tokens',
    'output.output_tokens': 'output tokens',
    'total_duration': 'scored in',
    'MRR': 'MRR',
    'HitDbRag': 'outcome',
    'total_cost': 'cost',
    'LLMJudge': 'correct',
    'LLMJudge reason': 'judgement',
}

# Under this a slice is too thin to carry its own label without landing on its neighbour's
MINIMUM_LABEL = 0.08

# The day alone wherever it is shown, since a full timestamp is cut off. The hour is a tooltip.
RUN_DATE_FORMAT = '%Y-%m-%d'
FULL_DATE_FORMAT = '%Y-%m-%d %H:%M'

# The whole summary on one line
SUMMARY_COLUMNS = 9

# st.metric draws its value at a size no parameter of its own reaches, and eight tiles across one row
# need it small enough to fit. These are the test ids this Streamlit build gives the label and value.
SUMMARY_STYLE = '''
<style>
[data-testid="stMetricValue"] { font-size: 1rem; }
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p { font-size: 0.72rem; }
</style>
'''

# A dataframe scrolls inside its own box past this many pixels, so a table is given the height of its rows
ROW_HEIGHT = 35

repository = buildEvaluationRunsRepository()
feedbackRepository = buildFeedbackRepository()


# Held for the session rather than built beside the repositories above, because a Rag opens an
# OpenAI client and this script runs top to bottom on every page: building it there would open one
# for whoever only came to read a report.
@st.cache_resource
def rag():
    return buildGenresRag()


# Every chart on the page is this one: a dict of label to fraction, drawn as a labelled donut. A
# score and a breakdown differ only in what fills the dict, so they are not two kinds of chart.
# The legend sits to the right, which is room Vega takes out of the width. It only overlapped the
# donut when it was underneath: the fit took the room out of the height, and these radii are absolute
# pixels that could not shrink along with it. Across a whole row there is width to spare.
def donut(slices, scale):
    data = pandas.DataFrame({'slice': list(slices), 'fraction': list(slices.values())})
    base = altair.Chart(data).encode(
        theta = altair.Theta('fraction:Q', stack = True),
        color = altair.Color(
            'slice:N',
            scale = scale,
            title = None,
            legend = altair.Legend(orient = 'right'),
        ),
        order = altair.Order('fraction:Q', sort = 'descending'),
        tooltip = ['slice:N', altair.Tooltip('fraction:Q', format = '.1%')],
    )
    # The white gap keeps neighbouring slices from reading as one
    arc = base.mark_arc(innerRadius = 45, outerRadius = 75, stroke = 'white', strokeWidth = 2)
    # Two slivers side by side sit at nearly the same angle, and Vega will happily write one number
    # over the other, so only a slice with room for it gets one. The rest are read underneath.
    labels = base.transform_filter(
        altair.datum.fraction >= MINIMUM_LABEL
    ).mark_text(radius = 96, size = 11).encode(
        text = altair.Text('fraction:Q', format = '.0%'),
        # Text wears ink colour; the slice beside it is what carries the identity
        color = altair.value('#5b5b66'),
    )

    return (arc + labels).properties(height = 300)


# A run that never scored one shows a dash rather than a bare "None"
def formatScore(score):
    return '{score:.2f}'.format(score = score) if score is not None else '—'


# The mean the evaluation itself worked out, or nothing when the run never scored that evaluator.
# Nothing here is averaged: what a run reports is what it stored.
def averageScore(run, name):
    return (run.getAverages() or {}).get('scores', {}).get(name)


# Where a rag run's answers ended up, as stored. Nothing for a retrieval run, which scores no outcome
def outcomesOf(run):
    return (run.getAverages() or {}).get('labels', {}).get(OUTCOME_LABEL)


# What each gauge is drawn from, under the heading it is drawn with. Nothing for a run stored before
# the rates were kept, which has no number anybody measured
def foundOf(run):
    rates = (run.getAverages() or {}).get(ASSERTION_RATES) or {}
    return {title: rates[name] for name, title in FOUND_CHARTS.items() if rates.get(name) is not None}


# A heading the contents can reach. Streamlit derives an anchor from the wording on its own, so
# naming it here is what keeps the link working when the wording is changed.
def section(title):
    st.subheader(title, anchor = SECTIONS[title])


# The sections this run actually draws, which is what the contents may offer. A retrieval run scores
# neither an outcome nor a genre found, and gets a shorter list rather than links to nothing.
def sectionsOf(run):
    drawn = [title for title, has in [(OUTCOMES, outcomesOf), (FOUND, foundOf)] if has(run)]
    return [*drawn, REPORT_SECTION]


# Where the report goes, before any of it. Sections are few and short enough to sit on one line.
def renderContents(run):
    st.markdown(' · '.join(
        '[{title}](#{anchor})'.format(title = title, anchor = SECTIONS[title])
            for title in sectionsOf(run)
    ))


# The only chart on the page: hit rate and MRR are scores, and a score drawn against its own
# remainder says nothing its tile does not.
def renderOutcomes(run):
    outcomes = outcomesOf(run)
    if not outcomes:
        return

    section(OUTCOMES)
    st.altair_chart(donut(outcomes, altair.Scale(scheme = 'tableau10')))


# A rate as a column filling from the bottom, one beside the other so they are read at a glance.
# Drawn as a fill over a full-height track rather than as a stack, so which part sits at the
# bottom is the layer order and never something Vega has to work out.
def gauges(rates):
    data = pandas.DataFrame({
        'gauge': list(rates),
        'rate': list(rates.values()),
        'track': [1.0] * len(rates),
    })
    # Left to right in the order they were asked for, whatever the headings sort as
    gauge = altair.X('gauge:N', title = None, sort = list(rates), axis = altair.Axis(labelAngle = 0))
    scale = altair.Scale(domain = [0, 1])

    track = altair.Chart(data).mark_bar(color = MISSING_COLOUR, size = GAUGE_WIDTH).encode(
        x = gauge,
        y = altair.Y('track:Q', title = None, scale = scale, axis = altair.Axis(format = '%')),
    )
    fill = altair.Chart(data).mark_bar(color = FOUND_COLOUR, size = GAUGE_WIDTH).encode(
        x = gauge,
        y = altair.Y('rate:Q', title = None, scale = scale),
        tooltip = [altair.Tooltip('gauge:N', title = FOUND_LABEL), altair.Tooltip('rate:Q', format = '.1%')],
    )
    # Held at the top of the column rather than at the top of the fill, which would leave the plot
    # on a rate near the whole and land on the axis on a rate near nothing
    label = altair.Chart(data).mark_text(baseline = 'top', dy = 8, size = 13).encode(
        x = gauge,
        y = altair.value(0),
        text = altair.Text('rate:Q', format = '.0%'),
        color = altair.value('#5b5b66'),
    )

    return (track + fill + label).properties(height = 260)


# How often the expected genre was found, at each of the two points it can be. A run stored before
# the rates were kept has none, and shows nothing rather than a chart of a number nobody measured.
def renderFound(run):
    charted = foundOf(run)
    if not charted:
        return

    section(FOUND)
    st.altair_chart(gauges(charted))


# A genre or instrument is named and described; the cell only has room for what it is called
def toNames(value):
    if not isinstance(value, list):
        return value

    return [named['name'] for named in value]


# The columns the report is actually read by, in the order it is read in
def orderColumns(frame):
    leading = [column for column in LEADING_COLUMNS if column in frame.columns]
    return frame[[*leading, *[column for column in frame.columns if column not in leading]]]


# One row per case, flattened out of the stored report. Each evaluator keeps the value it scored,
# under its own name, and loses its bookkeeping; otherwise fifty cases arrive as eighty columns.
def toCasesFrame(cases):
    frame = pandas.json_normalize(cases).drop(columns = CASE_NOISE, errors = 'ignore')
    scored = {
        column: column.split('.')[-2] for column in frame.columns
            if column.startswith(EVALUATOR_GROUPS) and column.endswith('.value')
                and column.split('.')[-2] not in HIDDEN_EVALUATORS
    }
    # Why an evaluator scored what it did, for the one evaluator that says so
    scored.update({
        column: '{name} reason'.format(name = column.split('.')[-2]) for column in frame.columns
            if column.endswith('.reason') and column.split('.')[-2] in REASONED_EVALUATORS
    })
    # Whatever is not the value an evaluator scored, the hidden ones included, goes with the bookkeeping
    bookkeeping = [
        column for column in frame.columns
            if column.startswith(EVALUATOR_GROUPS) and column not in scored
    ]
    frame = frame.drop(columns = bookkeeping).rename(columns = scored)

    for column in NAMED_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].map(toNames)

    frame = orderColumns(frame).rename(columns = CASE_LABELS)

    # Arrow cannot hold the lists a case carries, so what is left of them travels as text
    return frame.map(lambda value: ', '.join(value) if isinstance(value, list) else value)


def reportUrl(id):
    return '{path}?run={id}'.format(path = REPORT_PATH, id = id)


# One row per run, carrying the link its report is reached by. What a run scored belongs to the
# report, so the list only says which run it is and how to open it.
def toRunsFrame(runs):
    rows = [
        {
            'id': run.id,
            'created_at': run.created_at.strftime(RUN_DATE_FORMAT),
            'type': run.getType(),
            'retriever': run.retriever,
            'report': reportUrl(run.id),
        }
        for run in runs
    ]

    return pandas.DataFrame(rows).rename(columns = RUN_LABELS)


# The narrow columns, under whatever heading they are shown by
def narrowColumns():
    return {
        CASE_LABELS.get(column, column): st.column_config.TextColumn(width = 'small')
            for column in NARROW_COLUMNS
    }


# Streamlit scrolls a table past its default height, so every row is asked for on the page at once
def renderTable(frame, **options):
    st.dataframe(frame, hide_index = True, height = (len(frame) + 1) * ROW_HEIGHT + 3, **options)


# The run named by the query string, or nothing when it names none that exists
def loadRun(id):
    if id is None or not id.isdigit():
        return None

    return repository.load(int(id))


def renderSummary(run):
    st.markdown(SUMMARY_STYLE, unsafe_allow_html = True)

    # A tile still cuts off anything longer than its share of the row, so the day is what it shows
    # and the hour that tells two runs of the same day apart waits in the tooltip.
    summary = [
        ('Id', run.id),
        ('Type', run.getType()),
        ('Retriever', run.retriever),
        ('k', run.k),
        ('Embedding model', run.embedding_model),
        ('Date', run.created_at.strftime(RUN_DATE_FORMAT), run.created_at.strftime(FULL_DATE_FORMAT)),
        ('Hit rate', formatScore(run.hit_rate), 'How often the expected genre was retrieved at all'),
        ('MRR', formatScore(run.mrr), 'Mean reciprocal rank of the expected genre among the retrieved'),
    ]

    # Only a run that generates an answer takes time doing it, so a retrieval run shows no tile
    # rather than a dash where a number never existed
    seconds = averageScore(run, GENERATION_TIME_SCORE)
    if seconds is not None:
        summary.append((
            'Answer time',
            '{seconds:.2f} s'.format(seconds = seconds),
            'Mean seconds a case took to come back, as the run recorded it',
        ))

    for start in range(0, len(summary), SUMMARY_COLUMNS):
        row = summary[start:start + SUMMARY_COLUMNS]
        for column, [label, value, *tooltip] in zip(st.columns(SUMMARY_COLUMNS), row):
            column.metric(label, value, help = [*tooltip, None][0])


# The answer to a question, whether the index found anything or not. An empty retrieval is an answer
# of its own, exactly as the rag command reads it, and not a failure the page has to explain.
def askRag(question):
    try:
        return rag().query(question)
    except EmptyRetrievalError as error:
        return EmptyRagResponse(error.getQuery(), error.getDuration())


# One of the lists the answer named, each entry described under its own name. Always offered, even
# where the answer named nothing: an accordion that comes and goes with the answer reads as a
# missing list rather than as an empty one, and the two are worth telling apart.
def renderNamed(title, named, empty):
    with st.expander(title):
        if not named:
            st.caption(empty)
            return

        for item in named:
            st.markdown('**{name}**'.format(name = item['name']))
            st.write(item['description'])


# What the person asking made of the answer, stored under the conversation it was given in so the
# judge that will read the same answer back writes its verdict beside this one rather than over it.
def renderFeedback(conversation, question, answer):
    # Keyed by the conversation, or the thumb pressed on one answer would arrive already pressed on
    # the next one and rate an answer nobody had read yet
    thumb = st.feedback('thumbs', key = THUMBS_STATE.format(conversation = conversation))
    if thumb is None:
        return

    score = SCORES[thumb]
    # The widget hands its selection back on every rerun, and the rerun a thumb causes is only one
    # of them, so a verdict already stored is not written again on the next pass through the page.
    if st.session_state.get(SCORED_STATE) != [conversation, score]:
        feedbackRepository.save(conversation, Feedback.Source.USER, question, answer, score)
        st.session_state[SCORED_STATE] = [conversation, score]

    st.caption(FEEDBACK_THANKS)


# The answer as it was stored: what the LLM wrote, the genres and instruments it named, and the
# thumbs. Nothing at all before the first question of the session has been asked.
def renderAnswer():
    stored = st.session_state.get(ANSWER_STATE)
    if stored is None:
        return

    answer = stored['answer']
    st.divider()
    st.markdown(answer['answer'])

    for field, title in ANSWERED.items():
        renderNamed(title, answer[field], EMPTY_NAMED.format(named = field))

    renderFeedback(st.session_state[CONVERSATION_STATE], stored['query'], stored)


def chat():
    st.title('Chat')
    st.caption('Ask about a genre, what it sounds like or the instruments behind it.')

    # A form rather than a loose box and a button beside it. A text area only hands its contents to
    # the server when it loses the focus, so a question just typed into it was not there yet: the
    # button had nothing to enable itself on, and pressing it would have asked the question before.
    # A form submits the box and the press together, and its button is never disabled.
    with st.form(QUESTION_FORM, border = False):
        question = st.text_area('Your question', max_chars = QUESTION_LENGTH)
        sent = st.form_submit_button('Send', type = 'primary')

    if sent and not question.strip():
        st.warning(EMPTY_QUESTION)

    if sent and question.strip():
        # The answer on screen goes before the next one is asked for, so a query that takes its time
        # is never spent under the answer to a question nobody is asking any more
        st.session_state.pop(ANSWER_STATE, None)

        with st.spinner(SEARCHING):
            response = askRag(question)

        # Stored as the dict rather than the response, which is what the feedback row carries and
        # what the page reads back on every rerun from here on
        st.session_state[ANSWER_STATE] = response.toDict()
        # Minted with the answer, not with the thumb, so both verdicts on it share a conversation
        st.session_state[CONVERSATION_STATE] = feedbackRepository.nextConversation()

    renderAnswer()


def selection():
    st.title('Evaluations')
    st.caption('Filter the runs, then open one to see its report.')

    [typeColumn, modelColumn, dateColumn] = st.columns(3)
    # The options are whatever is stored, so a filter can never offer a value that empties the list
    types = typeColumn.multiselect('Type', repository.getTypes())
    embeddingModels = modelColumn.multiselect('Embedding model', repository.getEmbeddingModels())
    dates = dateColumn.date_input('Ran between', value = ())

    # The picker hands back nothing, one date or both, depending on how far through it the user is
    [since, until] = [*dates, None, None][:2]

    runs = repository.findFiltered(types, embeddingModels, since, until)
    if not runs:
        st.info('No evaluation run matches these filters.')
        return

    renderTable(
        toRunsFrame(runs),
        column_config = {RUN_LABELS['report']: st.column_config.LinkColumn(display_text = 'Open')},
    )


def report():
    run = loadRun(st.query_params.get('run'))
    if run is None:
        st.title('Report')
        st.warning('That evaluation run does not exist. Pick one from the list instead.')
        st.link_button('Back to the evaluations', EVALUATIONS_PATH)
        return

    st.title('Evaluation run {id}'.format(id = run.id))
    renderContents(run)
    renderSummary(run)

    renderOutcomes(run)
    renderFound(run)

    section(REPORT_SECTION)
    renderTable(toCasesFrame(run.report['cases']), column_config = narrowColumns())


# The default page always sits at "/", whatever url_path says, so the chat is the page the app opens
# on and the evaluations are reached by the path EVALUATIONS_PATH names.
st.navigation([
    st.Page(chat, title = 'Chat', default = True),
    st.Page(selection, title = 'Evaluations', url_path = 'evaluations'),
    st.Page(report, title = 'Report', url_path = 'report'),
]).run()
