def get_updater_status(job_id, scheduler) -> bool:
    return True if job_id in scheduler else False
