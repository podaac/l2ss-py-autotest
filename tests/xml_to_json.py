import sys
import json
from junitparser import JUnitXml, JUnitXmlError
import re

def extract_labels(case):
    """Extract labels based on test case results."""
    labels = []
    for result in case.result:
        if hasattr(result, "message") and "No granules found" in str(result.message):
            labels.append("No Granules")
        if hasattr(result, "message") and "There are no umm-v associated with this collection" in str(result.message):
            labels.append("No UMM-V")
        if hasattr(result, "message") and re.search(r"Failed: Timeout \(>\d+(\.\d+)?s\) from pytest-timeout", str(result.message)):
            labels.append("Timeout")
    if not labels:
        labels.append('Other')
    return labels

def determine_status(case):
    """Determine the status of a test case."""
    return str(case.result[0]) if case.result else "passed"

def determine_labels(stats):
    """Determine GitHub labels based on test statistics."""
    labels = set()
    if stats["tests_succ"] > 0 and stats["tests_fail"] == 0 and stats["tests_error"] == 0:
        labels.add("verified")
    if stats["tests_fail"] > 0 or stats["tests_error"] > 0:
        labels.update(["failed verification", "bug"])
    if stats["tests_skip"] > 0:
        labels.add("tests skipped")
    if not labels:
        labels.add("unverified")
    return labels

def main():
    """Main function to parse XML and generate JSON."""
    if len(sys.argv) != 3:
        print("Usage: python xml_to_json.py <input.xml> <output.json>")
        sys.exit(1)

    xml_file = sys.argv[1]
    json_file = sys.argv[2]

    try:
        xml = JUnitXml.fromfile(xml_file)
    except JUnitXmlError as e:
        print(f"Error parsing XML file: {e}")
        sys.exit(1)

    labels = set()
    test_cases = []

    for suite in xml:
        for case in suite:
            status = determine_status(case)
            case_labels = extract_labels(case)
            labels.update(case_labels)
            test_cases.append({
                "name": case.name,
                "classname": case.classname,
                "status": status
            })

    stats = {
        "tests": xml.tests,
        "tests_succ": xml.tests - xml.failures - xml.errors - xml.skipped,
        "tests_fail": xml.failures,
        "tests_error": xml.errors,
        "tests_skip": xml.skipped
    }

    # Determine GitHub labels
    labels.update(determine_labels(stats))

    result = {
        "stats": stats,
        "cases": test_cases,
        "apply_labels": list(labels),
    }

    try:
        with open(json_file, "w") as f:
            json.dump(result, f, indent=2)
    except IOError as e:
        print(f"Error writing JSON file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()