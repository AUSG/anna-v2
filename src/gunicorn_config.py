"""예약 작업은 앱 import가 아니라 worker 초기화가 끝난 뒤 시작한다."""


def post_worker_init(worker):
    from anna import start_jobs

    start_jobs(worker.wsgi)
