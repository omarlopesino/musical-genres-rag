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

from musical_genres_rag.services import buildEvaluationRunsRepository

# Streamlit renders every bare expression a script leaves at module level, a docstring above a
# function included, so everything explanatory in this file is a comment instead.

# A report is reached by its own URL rather than by a click, so an Airflow task can link the run it
# just finished. The page the app navigates to and the page Airflow links are the same one.
REPORT_PATH = '/report'

# The label a rag run stores its outcome breakdown under. Retrieval runs never score it
OUTCOME_LABEL = 'HitDbRag'

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
    'output.query',
    'output.retrieved',
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
]

# The answer names each genre and instrument with a description attached. Only the names fit a cell
NAMED_COLUMNS = ['output.answer.genres', 'output.answer.instruments']

# What a case asked and what came back lead the table, side by side, whatever order the report
# serialized its fields in.
LEADING_COLUMNS = ['metadata.question', 'output.answer.answer']

# Held narrow, or the long prose takes the width from everything the case scored
NARROW_COLUMNS = ['metadata.question', 'output.answer.answer']

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
    'output.kind': 'asked about',
    'output.genre': 'expected genre',
    'output.query': 'query',
    'output.answer.answer': 'answer',
    'output.answer.genres': 'answered genres',
    'output.answer.instruments': 'answered instruments',
    'output.duration': 'seconds',
    'output.input_tokens': 'input tokens',
    'output.output_tokens': 'output tokens',
    'total_duration': 'scored in',
    'HitRate': 'retrieved',
    'MRR': 'MRR',
    'HitDbRag': 'outcome',
    'GenreRagGenreHit': 'named the genre',
    'GenreRagGenreMrr': 'genre MRR',
    'total_cost': 'cost',
}

# Under this a slice is too thin to carry its own label without landing on its neighbour's
MINIMUM_LABEL = 0.08

# The day alone wherever it is shown, since a full timestamp is cut off. The hour is a tooltip.
RUN_DATE_FORMAT = '%Y-%m-%d'
FULL_DATE_FORMAT = '%Y-%m-%d %H:%M'

# The whole summary on one line
SUMMARY_COLUMNS = 8

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


# Where a rag run's answers ended up, read as stored. The only chart on the page: hit rate and MRR
# are scores, and a score drawn against its own remainder says nothing its tile does not.
# A retrieval run never scores an outcome, and simply shows nothing.
def renderOutcomes(run):
    outcomes = (run.getAverages() or {}).get('labels', {}).get(OUTCOME_LABEL)
    if not outcomes:
        return

    st.subheader('Outcomes')
    st.altair_chart(donut(outcomes, altair.Scale(scheme = 'tableau10')))


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

    for start in range(0, len(summary), SUMMARY_COLUMNS):
        row = summary[start:start + SUMMARY_COLUMNS]
        for column, [label, value, *tooltip] in zip(st.columns(SUMMARY_COLUMNS), row):
            column.metric(label, value, help = [*tooltip, None][0])


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
        st.link_button('Back to the evaluations', '/')
        return

    st.title('Evaluation run {id}'.format(id = run.id))
    renderSummary(run)

    renderOutcomes(run)

    st.subheader('Cases')
    renderTable(toCasesFrame(run.report['cases']), column_config = narrowColumns())


# The default page always sits at "/", whatever url_path says, so the selection is the page the app opens on
st.navigation([
    st.Page(selection, title = 'Evaluations', default = True),
    st.Page(report, title = 'Report', url_path = 'report'),
]).run()
