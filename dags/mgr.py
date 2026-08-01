from airflow.sdk import DAG, BaseOperatorLink, Param
from airflow.providers.http.operators.http import HttpOperator
from airflow.providers.http.sensors.http import HttpSensor
from datetime import datetime, timedelta
import attrs
import json
import logging

log = logging.getLogger(__name__)

# Where the app is reached is the connection's business, so the endpoints below are paths
HTTP_CONN_ID = "musical_genres_rag"

# Named one by one rather than read from the app: a dag is parsed by the scheduler, which imports
# none of the project, so this list is kept in step with services.ENGINES by hand.
DEFAULT_PARAMS = {
    "engine": Param(
        "postgres_text",
        enum = [
            "postgres_text",
            "postgres_embed",
            "postgres_hybrid"
        ]
    )
}

"""What the judge is run with instead. It searches no index, so it is told how much to read rather
than what to read it through: every answer it reads is a paid call, and a run every five minutes is
bounded by this rather than by how much feedback has arrived since the last one."""
JUDGE_PARAMS = {
    "limit": Param(
        100,
        type = "integer",
        minimum = 1
    )
}

# Any moment already past will do: nothing is caught up on, so this only says the schedule has begun
SCHEDULE_START = datetime(2026, 1, 1)

def OperationResponseCheck(response):
    log.info(response.json())
    return "running" in response.json()["status"]

def ProgressFinishedCheck(response):
    response = response.json()
    log.info(response)
    log.info("Progress: " + str(response["percent"]) + "%")
    return response["done"]

"""A button on a task, named as the file the operation it waited for wrote"""
@attrs.define()
class AttachmentLink(BaseOperatorLink):
    name: str = "Attachment"

    @property
    def xcom_key(self):
        return "attachment_url"

    # Asked for the button's url once the task is over, and answers with the one the check kept
    def get_link(self, operator, *, ti_key):
        return ti_key.xcom_pull(task_ids = ti_key.task_id, key = self.xcom_key, default = "") or ""

# The sensor of the checks below, carrying a button named after what they waited for
class LinkedHttpSensor(HttpSensor):
    def __init__(self, link_name = "Attachment", **kwargs):
        super().__init__(**kwargs)
        self.operator_extra_links = (AttachmentLink(link_name),)

"""Waits for the operation to be over, and keeps the link to the file it wrote"""
def AttachmentFinishedCheck(response, task_instance):
    response = response.json()
    log.info(response)
    log.info("Progress: " + str(response["percent"]) + "%")

    if not response["done"]:
        return False

    link = (response["result"] or {}).get("link")
    if link:
        log.info("Attachment: " + link)
        task_instance.xcom_push(key = "attachment_url", value = link)

    return True

"""Waits for the operation to be over, logs how much of it there turned out to be, and keeps the
link to what it wrote.

For the operations that produce rows rather than a file: the count is what they did, and the link
is where the rows they touched are read back.
"""
def TotalFinishedCheck(response, task_instance):
    response = response.json()
    log.info(response)
    log.info("Progress: " + str(response["percent"]) + "%")

    if not response["done"]:
        return False

    result = response["result"] or {}
    log.info("Total processed: " + str(result.get("total")))

    link = result.get("link")
    if link:
        log.info("Feedback: " + link)
        task_instance.xcom_push(key = "attachment_url", value = link)

    return True

"""
Index all musical genres data.
"""
with DAG(
    dag_id="ingest",
    dag_display_name="1. Ingest",
    params = DEFAULT_PARAMS,
    description="Index all musical genres data",
    tags = ["musical_genres_rag"]
) as dag:
    ingest = HttpOperator(
        task_id="ingest",
        http_conn_id=HTTP_CONN_ID,
        method="POST",
        endpoint="/ingest",
        data=json.dumps({"engine": "{{ params.engine }}"}),
        headers={"Content-Type": "application/json"},
        response_check=OperationResponseCheck,
        response_filter=lambda response: response.json()["task_id"],
        dag=dag,
    )

    progress = HttpSensor(
        task_id="ingest_finished",
        method="GET",
        http_conn_id=HTTP_CONN_ID,
        endpoint="/progress/{{ ti.xcom_pull(task_ids='ingest') }}",
        request_params={},
        response_check=ProgressFinishedCheck,
        poke_interval=5,
        dag=dag,
    )

    ingest >> progress

"""
Generates ground truth.

No engine, unlike the dags either side of it: the questions are written from the repository and no
index is searched, and the one set they make is what every engine is then scored against.
"""
with DAG(
    dag_id="ground_truth",
    dag_display_name="2. Ground truth",
    description="Generates ground truth for actual data",
    tags = ["musical_genres_rag"]
) as dag:
    ground_truth = HttpOperator(
        task_id="ground_truth",
        http_conn_id=HTTP_CONN_ID,
        method="POST",
        endpoint="/ground-truth",
        data=json.dumps({}),
        headers={"Content-Type": "application/json"},
        response_check=OperationResponseCheck,
        response_filter=lambda response: response.json()["task_id"],
        dag=dag,
    )

    progress = LinkedHttpSensor(
        task_id="ground_truth_finished",
        link_name="Ground Truth CSV",
        method="GET",
        http_conn_id=HTTP_CONN_ID,
        endpoint="/progress/{{ ti.xcom_pull(task_ids='ground_truth') }}",
        request_params={},
        response_check=AttachmentFinishedCheck,
        poke_interval=5,
        dag=dag,
    )

    ground_truth >> progress
    
"""
Creates answers froom ground truth.
"""
with DAG(
    dag_id="create_answers",
    dag_display_name="3. Create answers",
    params = DEFAULT_PARAMS,
    description="Given the ground truth, creates the answers",
    tags = ["musical_genres_rag"]
) as dag:
    create_answers = HttpOperator(
        task_id="create_answers",
        http_conn_id=HTTP_CONN_ID,
        method="POST",
        endpoint="/create-answers",
        data=json.dumps({"engine": "{{ params.engine }}"}),
        headers={"Content-Type": "application/json"},
        response_check=OperationResponseCheck,
        response_filter=lambda response: response.json()["task_id"],
        dag=dag,
    )

    progress = LinkedHttpSensor(
        task_id="create_answers_finished",
        link_name="Answers generated as JSON",
        method="GET",
        http_conn_id=HTTP_CONN_ID,
        endpoint="/progress/{{ ti.xcom_pull(task_ids='create_answers') }}",
        request_params={},
        response_check=AttachmentFinishedCheck,
        poke_interval=5,
        dag=dag,
    )

    create_answers >> progress
    
"""
Runs evaluation from the latest answer set.
"""
with DAG(
    dag_id="evaluate_retrieval",
    dag_display_name="4. Evaluate retrieval",
    params = DEFAULT_PARAMS,
    description="Evaluates the retrieval of questions",
    tags = ["musical_genres_rag"]
) as dag:
    evaluate_retrieval = HttpOperator(
        task_id="evaluate_retrieval",
        http_conn_id=HTTP_CONN_ID,
        method="POST",
        endpoint="/evaluate-retrieval",
        data=json.dumps({"engine": "{{ params.engine }}"}),
        headers={"Content-Type": "application/json"},
        response_check=OperationResponseCheck,
        response_filter=lambda response: response.json()["task_id"],
        dag=dag,
    )

    progress = LinkedHttpSensor(
        task_id="evaluate_rag_finished",
        link_name="Retrieval evaluation results",
        method="GET",
        http_conn_id=HTTP_CONN_ID,
        endpoint="/progress/{{ ti.xcom_pull(task_ids='evaluate_retrieval') }}",
        request_params={},
        response_check=AttachmentFinishedCheck,
        poke_interval=5,
        dag=dag,
    )

    evaluate_retrieval >> progress

"""
Runs evaluation from the latest answer set.
"""
with DAG(
    dag_id="evaluate_rag",
    dag_display_name="5. Evaluate RAG",
    params = DEFAULT_PARAMS,
    description="Evaluates the given answers",
    tags = ["musical_genres_rag"]
) as dag:
    evaluate_rag = HttpOperator(
        task_id="evaluate_rag",
        http_conn_id=HTTP_CONN_ID,
        method="POST",
        endpoint="/evaluate-rag",
        data=json.dumps({"engine": "{{ params.engine }}"}),
        headers={"Content-Type": "application/json"},
        response_check=OperationResponseCheck,
        response_filter=lambda response: response.json()["task_id"],
        dag=dag,
    )

    progress = LinkedHttpSensor(
        task_id="evaluate_rag_finished",
        link_name="RAG evaluation results",
        method="GET",
        http_conn_id=HTTP_CONN_ID,
        endpoint="/progress/{{ ti.xcom_pull(task_ids='evaluate_rag') }}",
        request_params={},
        response_check=AttachmentFinishedCheck,
        poke_interval=5,
        dag=dag,
    )

    evaluate_rag >> progress

"""
Judges the answers people left feedback on.

The only dag that runs itself: feedback arrives whenever somebody presses a thumb, so this reads
what has arrived every five minutes rather than waiting to be asked. One run at a time, and no
catching up on the schedules that passed while it was off — what is pending is pending whenever
the next run starts, and reading it twice would only spend the calls twice.
"""
with DAG(
    dag_id="feedback_judge",
    dag_display_name="6. Feedback judge",
    params = JUDGE_PARAMS,
    description="Scores the answers people left feedback on",
    schedule = timedelta(minutes = 5),
    start_date = SCHEDULE_START,
    catchup = False,
    max_active_runs = 1,
    tags = ["musical_genres_rag"]
) as dag:
    feedback_judge = HttpOperator(
        task_id="feedback_judge",
        http_conn_id=HTTP_CONN_ID,
        method="POST",
        endpoint="/feedback-judge",
        data=json.dumps({"limit": "{{ params.limit }}"}),
        headers={"Content-Type": "application/json"},
        response_check=OperationResponseCheck,
        response_filter=lambda response: response.json()["task_id"],
        dag=dag,
    )

    progress = LinkedHttpSensor(
        task_id="feedback_judge_finished",
        link_name="Feedback",
        method="GET",
        http_conn_id=HTTP_CONN_ID,
        endpoint="/progress/{{ ti.xcom_pull(task_ids='feedback_judge') }}",
        request_params={},
        response_check=TotalFinishedCheck,
        poke_interval=5,
        dag=dag,
    )

    feedback_judge >> progress
