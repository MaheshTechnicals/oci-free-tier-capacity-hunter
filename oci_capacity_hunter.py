import os
import sys
import time
import random
import logging
import oci
from dotenv import load_dotenv

# =========================================================
# LOAD CONFIG FROM .env FILE
# =========================================================
load_dotenv()

REQUIRED_VARS = [
    "OCI_USER_OCID",
    "OCI_FINGERPRINT",
    "OCI_KEY_FILE",
    "OCI_TENANCY_OCID",
    "OCI_REGION",
    "OCI_STACK_ID",
]

missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    print(f"❌ Missing required environment variables: {', '.join(missing)}")
    print("👉 Copy .env.example to .env and fill in your values. See README.md for details.")
    sys.exit(1)

config = {
    "user": os.getenv("OCI_USER_OCID"),
    "fingerprint": os.getenv("OCI_FINGERPRINT"),
    "key_file": os.getenv("OCI_KEY_FILE"),
    "tenancy": os.getenv("OCI_TENANCY_OCID"),
    "region": os.getenv("OCI_REGION"),
}

# Optional: only needed if your key has a passphrase
key_passphrase = os.getenv("OCI_KEY_PASSPHRASE")
if key_passphrase:
    config["pass_phrase"] = key_passphrase

STACK_ID = os.getenv("OCI_STACK_ID")

if not os.path.isfile(config["key_file"]):
    print(f"❌ Private key file not found at: {config['key_file']}")
    print("👉 Check OCI_KEY_FILE path in your .env file.")
    sys.exit(1)

# =========================================================
# POLLING TUNING
# =========================================================
MIN_WAIT = int(os.getenv("MIN_WAIT", 90))
MAX_WAIT = int(os.getenv("MAX_WAIT", 240))
RATE_LIMIT_BASE = int(os.getenv("RATE_LIMIT_BASE", 60))
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", 600))
COOLDOWN_EVERY = int(os.getenv("COOLDOWN_EVERY", 15))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", 20))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("capacity_hunter")


def human_wait(base_min, base_max):
    """Randomized wait that doesn't follow a fixed cadence."""
    wait = random.uniform(base_min, base_max)
    time.sleep(wait)
    return wait


def run_capacity_hunter():
    resource_manager = oci.resource_manager.ResourceManagerClient(config)

    attempt = 1
    consecutive_failures = 0

    log.info("Oracle Cloud Capacity Hunter Initialized.")
    log.info(f"Target Stack: {STACK_ID}")

    while True:
        log.info(f"=== Attempt #{attempt} ===")

        try:
            job_details = oci.resource_manager.models.CreateJobDetails(
                stack_id=STACK_ID,
                job_operation_details=oci.resource_manager.models.CreateApplyJobOperationDetails(
                    operation="APPLY",
                    execution_plan_strategy="AUTO_APPROVED"
                )
            )

            job = resource_manager.create_job(job_details).data
            log.info(f"Deployment job created: {job.id}")
            log.info("Waiting for hardware allocation result...")

            poll_start = time.time()
            while job.lifecycle_state in ["ACCEPTED", "IN_PROGRESS"]:
                time.sleep(random.uniform(8, 15))
                job = resource_manager.get_job(job.id).data
                if time.time() - poll_start > 600:
                    log.warning("Job poll taking unusually long, breaking out to re-check state.")
                    break

            if job.lifecycle_state == "SUCCEEDED":
                log.info("SUCCESS! Instance has been claimed.")
                log.info("Check OCI Console -> Compute -> Instances.")
                break
            else:
                log.warning(f"Allocation status: {job.lifecycle_state}. Slot unavailable.")
                consecutive_failures += 1
                attempt += 1

        except oci.exceptions.ServiceError as e:
            if e.status == 429:
                sleep_time = min(RATE_LIMIT_BASE * (2 ** min(consecutive_failures, 4)), RATE_LIMIT_MAX)
                sleep_time += random.uniform(1, 10)
                log.warning(f"Rate limited (429). Backing off {sleep_time:.0f}s.")
                time.sleep(sleep_time)
            elif e.status in (401, 403):
                log.error(f"Auth/permission error ({e.status}): {e.message}")
                log.error("Stopping — retrying auth failures repeatedly is a strong abuse signal.")
                sys.exit(1)
            else:
                log.error(f"OCI API Error: {e.message}")
                consecutive_failures += 1

        except Exception as e:
            log.error(f"Unexpected Error: {str(e)}")
            consecutive_failures += 1

        if consecutive_failures and consecutive_failures % COOLDOWN_EVERY == 0:
            log.info(f"{consecutive_failures} consecutive misses — cooling down {COOLDOWN_MINUTES} min.")
            time.sleep(COOLDOWN_MINUTES * 60)
        else:
            wait = human_wait(MIN_WAIT, MAX_WAIT)
            log.info(f"Next attempt in {wait:.0f}s.")


if __name__ == "__main__":
    run_capacity_hunter()
