from prometheus_client import multiprocess


def child_exit(server, worker):
    # Marks the process as dead in the case that the
    # process crashes.
    multiprocess.mark_process_dead(worker.pid)
