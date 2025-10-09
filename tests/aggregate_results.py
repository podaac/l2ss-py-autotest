import glob
import json
import os


def main():
    job_status_files = glob.glob(os.path.join('job-status', '*', 'job_status.json'))
    failed = False
    for fpath in job_status_files:
        with open(fpath) as f:
            data = json.load(f)
        if data.get('status') != 'success':
            url = data.get('url', '')
            reason = data.get('reason', '')
            print(f"FAILED JOB: {url}")
            print("REGRESSION RESULTS:")
            try:
                # Pretty print the JSON if possible
                reason_json = json.loads(reason)
                print(json.dumps(reason_json, indent=2))
            except Exception:
                print(reason)
            print("----------------------")
            failed = True
    if not failed:
        print("No failed jobs.")

if __name__ == "__main__":
    main()
