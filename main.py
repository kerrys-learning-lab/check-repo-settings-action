#! /usr/bin/env python3
""" Queries a repository to verify (assert) the repository's settings match the
    desired settings specified via YAML.

    Looks for desired configuration settings in the repository root
    (${GITHUB_WORKSPACE}/.repository-settings.yaml) and in the action's
    defaults (${CONFIGDIR}/default-repository-settings.yaml, where CONFIGDIR
    defaults to /etc/repository-settings).
    
    The repository owner and name are taken from GITHUB_REPOSITORY.  The token
    is taken from INPUT_GITHUB_TOKEN."""
import argparse
import enum
import logging
import os
import re
import sys
import rich.console
import rich.logging
import rich.progress
import rich.table
import requests
import yaml

REPOSITORY_SETTINGS_FILE_PATH = os.path.join(
    os.environ.get("GITHUB_WORKSPACE", "."), ".repository-settings.yaml"
)
DEFAULT_SETTINGS_FILE_PATH = os.path.join(
    os.environ.get("CONFIGDIR", "/etc/repository-settings"),
    "default-repository-settings.yaml",
)
SUBSTITUTION_REGEX = re.compile("<(?P<key>.*)>")


def compare_values(value, reference_value, name=[]):
    """Recursively compares value to reference_value, returning a dictionary
    containing any mismatches."""
    name = name if isinstance(name, list) else [name]
    result = {}
    if isinstance(reference_value, dict):
        try:
            for key, val in reference_value.items():
                result = result | compare_values(value[key], val, [*name, key])
        except Exception as ex:
            logger.error(f"Unable to compare values for '{'.'.join(name)}': {ex}")
            result[".".join(name)] = {"current": "UNKNOWN", "desired": reference_value}
    elif isinstance(reference_value, list):
        try:
            # This approach performs a deep comparison of every element of the
            # array.  To simply check presence in the array, use assert_in_array.
            for index, val in enumerate(reference_value):
                result = result | compare_values(value[index], val, [*name, str(index)])
        except Exception as ex:
            logger.error(f"Unable to compare list values: {ex}")
            result[".".join(name)] = {"current": "UNKNOWN", "desired": ",".join(reference_value)}
    elif reference_value != value:
        result[".".join(name)] = {"current": value, "desired": reference_value}
    return result


def compare_array(gh_data: list, reference_values: list, key=None):
    """Checks that gh_data contains each value in reference_values."""
    errors = {}
    values = [v[key] for v in gh_data] if key else [*gh_data]
    for index, val in enumerate(reference_values):
        if val not in values:
            errors[f"[{index}]"] = {"current": "None", "desired": val}
    return errors


def substitute(value, substitutions: dict) -> dict:
    """Performs deep substitution on value, replacing <foo.bar> with the
    content of substitutions["foo"]["bar"]."""

    def _deep_get(value: dict, key: str):
        key_list = key.split(".")
        val = dict(value)
        while key_list:
            k = key_list.pop(0)
            val = val[k]
        return val

    def _lookup_substitution_value(substitution_value: str, substitutions: dict):
        for key in [substitution_value, f"defaults.{substitution_value}"]:
            try:
                return _deep_get(substitutions, key)
            except KeyError:
                pass
            except TypeError:
                pass

        raise RuntimeError(f"Unable to find substitution for {substitution_value}")

    if isinstance(value, dict):
        result = {}
        for key, val in value.items():
            key = substitute(key, substitutions)
            result[key] = substitute(val, substitutions)
        return result
    elif isinstance(value, list):
        return [substitute(val, substitutions) for val in value]
    elif isinstance(value, str):
        while True:
            match = SUBSTITUTION_REGEX.search(value)
            if match:
                sub = _lookup_substitution_value(match.group("key"), substitutions)
                value = value[: match.start()] + sub + value[match.end() :]
            else:
                break
        return value
    else:
        return value


def recursive_merge(dest: dict, source: dict):
    """Non-destructively merges source into dest"""
    for source_key, source_value in source.items():
        if source_key not in dest:
            dest[source_key] = source_value
        elif isinstance(source_value, dict):
            dest[source_key] = recursive_merge(dest[source_key], source_value)

    return dest


def _load_project_settings():
    project_settings = {}
    for settings_file_path in [
        REPOSITORY_SETTINGS_FILE_PATH,
        DEFAULT_SETTINGS_FILE_PATH,
    ]:
        try:
            with open(settings_file_path) as settings_file:
                logger.debug(f"Using settings from {settings_file_path}")
                project_settings = project_settings | yaml.safe_load(settings_file)
        except OSError:
            pass

    project_settings = substitute(project_settings, dict(project_settings))

    return recursive_merge(project_settings, project_settings.get("defaults", {}))


class ResultType(str, enum.Enum):
    """Valid result types"""

    ERROR = "ERROR"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    IGNORED = "IGNORED"


class ResultsTable:
    """Creates tabular output of the results"""

    RESULTS_COLOR = {
        ResultType.ERROR: "red",
        ResultType.FAILED: "red",
        ResultType.SUCCESS: "green",
        ResultType.IGNORED: "dim",
    }

    def __init__(self) -> None:
        self.table = rich.table.Table(show_header=True)
        self.table.add_column("Test")
        self.table.add_column("Result", width=10)
        self.results = {r: 0 for r in ResultType}

    @property
    def ignored(self):
        """Return the number of ignored tests"""
        return self.results[ResultType.IGNORED]

    @property
    def success(self):
        """Return the number of successful tests"""
        return self.results[ResultType.SUCCESS]

    @property
    def failed(self):
        """Return the number of failed tests"""
        return self.results[ResultType.FAILED]

    @property
    def error(self):
        """Return the number of errors (incomplete tests)"""
        return self.results[ResultType.ERROR]

    def add_results(
        self, test_name: str, test_spec: dict, result_type: ResultType, mismatches={}
    ):
        """Adds the result of a single test assertion."""
        color = ResultsTable.RESULTS_COLOR[result_type]
        self.table.add_row(test_name, f"[{color}]{result_type.name}[/{color}]")
        self.results[result_type] = self.results[result_type] + 1
        if result_type == ResultType.FAILED or result_type == ResultType.ERROR:
            for k in sorted(mismatches.keys()):
                desired = mismatches[k]["desired"]
                current = mismatches[k]["current"]
                self.table.add_row(
                    f"   - [dim][yellow][italic]{k}[/italic] should be [green]{desired}[/green] (currently [red]{current}[/red])[/yellow][/dim]",
                    "",
                )
            for hint in test_spec.get("hints", []):
                self.table.add_row(f"   - [dim]{hint}[/dim]", "")

    def print(self):
        """Print the results table to the console"""
        console = rich.console.Console()
        console.print(self.table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify repository settings.")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    # Set up logging ...
    logging.basicConfig(
        # format="%(asctime)s - %(levelname)-7s - %(name)20s - %(message)s",
        format="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
        handlers=[rich.logging.RichHandler()],
    )

    for logger in ["urllib3", "github"]:
        logging.getLogger(logger).setLevel(logging.ERROR)

    logger = logging.getLogger(os.path.basename(sys.argv[0]))

    project_settings = _load_project_settings()

    if not project_settings:
        raise RuntimeError()

    owner_name, _, repo_name = os.environ["GITHUB_REPOSITORY"].partition("/")
    github_token = os.environ.get("INPUT_GITHUB_TOKEN")

    logger.info(f"Checking repository: {repo_name} ({owner_name})")

    if not github_token:
        logger.error(f"INPUT_GITHUB_TOKEN is empty!")
        logger.error(
            f"Verify that this repository is able to access organization secrets."
        )
        logger.error(f"(Start by ensuring that this repository is public)")
        sys.exit(-1)

    output = ResultsTable()
    for test_name, test_spec in rich.progress.track(
        project_settings.get("tests", {}).items(),
        description=f"Validating settings for repository '{repo_name}'...",
    ):
        test_name = test_name.format(owner=owner_name, repo=repo_name)

        if test_spec.get("ignore", False):
            output.add_results(test_name, test_spec, ResultType.IGNORED)
            continue

        resource_path = test_spec["path"].format(owner=owner_name, repo=repo_name)
        resource_path = "https://api.github.com/" + resource_path
        logger.debug(f"Querying {resource_path}")
        try:
            result = requests.get(
                resource_path,
                headers={"Authorization": f"Bearer {github_token}"},
            )
            result.raise_for_status()
            mismatches = {}
            if "json" in test_spec:
                mismatches = compare_values(result.json(), test_spec["json"])
            elif "array" in test_spec:
                mismatches = compare_array(
                    result.json(), test_spec["array"], key=test_spec.get("key")
                )

            output.add_results(
                test_name,
                test_spec,
                ResultType.FAILED if mismatches else ResultType.SUCCESS,
                mismatches=mismatches,
            )

        except requests.exceptions.HTTPError:
            output.add_results(test_name, test_spec, ResultType.ERROR)

    output.print()
    sys.exit(
        0
        if os.environ.get("INPUT_IGNORE_FAILURES", "false").lower() == "true"
        else (output.error + output.failed)
    )
