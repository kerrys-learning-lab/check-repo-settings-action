#! /usr/bin/env python3
""" Uses the Python Github API (ghapi) to query a repository and verify
    (assert) the repository's settings match the desired settings specified
    via YAML.

    Looks for desired configuration settings in the repository root
    (${GITHUB_WORKSPACE}/.repository-settings.yaml) and in the action's
    defaults (${CONFIGDIR}/default-repository-settings.yaml, where CONFIGDIR
    defaults to /etc/repository-settings).
    
    The repository owner and name are taken from GITHUB_REPOSITORY.  The token
    is taken from INPUT_GITHUB_TOKEN."""
import argparse
import logging
import os
import re
import sys
import ghapi.all
import yaml

REPOSITORY_SETTINGS_FILE_PATH = os.path.join(
    os.environ.get("GITHUB_WORKSPACE", "."), ".repository-settings.yaml"
)
DEFAULT_SETTINGS_FILE_PATH = os.path.join(
    os.environ.get("CONFIGDIR", "/etc/repository-settings"),
    "default-repository-settings.yaml",
)
SUBSTITUTION_REGEX = re.compile("<(?P<key>.*)>")


class SettingsMismatchError(AssertionError):
    """Raised when a repository setting does not match the desired value"""

    def __init__(self, mismatches: dict = {}):
        super().__init__()
        self.mismatches = mismatches

    def __bool__(self) -> bool:
        return bool(self.mismatches)


def _recursive_assert_value(value, reference_value, name=[]):
    """Recursively compares value to reference_value, returning a dictionary
    containing any mismatches."""
    name = name if isinstance(name, list) else [name]
    result = {}
    if isinstance(reference_value, dict):
        for key, val in reference_value.items():
            result = result | _recursive_assert_value(value[key], val, [*name, key])
    elif isinstance(reference_value, list):
        # This approach performs a deep comparison of every element of the
        # array.  To simply check presence in the array, use assert_in_array.
        for index, val in enumerate(reference_value):
            result = result | _recursive_assert_value(
                value[index], val, [*name, str(index)]
            )
    elif reference_value != value:
        result[".".join(name)] = {"current": value, "desired": reference_value}
    return result


def assert_values(gh_data, reference_values, name=[]):
    """Asserts that gh_data contains values matching reference_values, else
    raises SettingsMismatchError."""
    errors = _recursive_assert_value(gh_data, reference_values, name)
    if errors:
        raise SettingsMismatchError(errors)


def assert_in_array(gh_data, reference_values, name="array"):
    """Asserts that gh_data contains each value in reference_values, else
    raises SettingsMismatchError."""
    errors = {}
    for index, val in enumerate(reference_values):
        if val not in gh_data:
            errors[f"{name}[{index}]"] = {"current": "None", "desired": val}
    if errors:
        raise SettingsMismatchError(errors)


def _deep_get(value: dict, key: str):
    key_list = key.split(".")
    val = dict(value)
    while key_list:
        k = key_list.pop(0)
        val = val[k]
    return val


def _substitute_key(substitution_key: str, substitutions: dict):
    for key in [substitution_key, f"defaults.{substitution_key}"]:
        try:
            return _deep_get(substitutions, key)
        except KeyError:
            pass
        except TypeError:
            pass

    raise RuntimeError(f"Unable to find substitution for {substitution_key}")


def _substitute(dest: dict, substitutions: dict = None) -> dict:
    result = {}
    substitutions = substitutions if substitutions is not None else dict(dest)
    for key, value in dest.items():
        match = SUBSTITUTION_REGEX.match(key)
        key = _substitute_key(match.group("key"), substitutions) if match else key

        result[key] = (
            _substitute(value, substitutions) if isinstance(value, dict) else value
        )

    return result


def _recursive_merge(dest: dict, source: dict):
    for source_key, source_value in source.items():
        if source_key not in dest:
            dest[source_key] = source_value
        elif isinstance(source_value, dict):
            dest[source_key] = _recursive_merge(dest[source_key], source_value)

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

    project_settings = _substitute(project_settings)

    return _recursive_merge(project_settings, project_settings.get("defaults", {}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify repository settings.")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    # Set up logging ...
    logging.basicConfig(
        format="%(asctime)s - %(levelname)-7s - %(name)20s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    for logger in ["urllib3", "github"]:
        logging.getLogger(logger).setLevel(logging.ERROR)

    if sys.stderr.isatty():
        logging.addLevelName(
            logging.WARNING,
            f"\033[1;31m{logging.getLevelName(logging.WARNING)}  \033[1;0m",
        )
        logging.addLevelName(
            logging.ERROR, f"\033[1;31m{logging.getLevelName(logging.ERROR)}  \033[1;0m"
        )

    logger = logging.getLogger(os.path.basename(sys.argv[0]))

    project_settings = _load_project_settings()

    if not project_settings:
        raise RuntimeError()

    owner_name, _, repo_name = os.environ["GITHUB_REPOSITORY"].partition("/")

    logger.info(f"Checking repository: {repo_name} ({owner_name})")

    if not os.environ["INPUT_GITHUB_TOKEN"]:
        logger.error(f"INPUT_GITHUB_TOKEN is empty!")
        logger.error(
            f"Verify that this repository is able to access organization secrets."
        )
        logger.error(f"(Start by ensuring that this repository is public)")
        sys.exit(-1)

    client = ghapi.all.GhApi(
        owner=owner_name,
        repo=repo_name,
        token=os.environ["INPUT_GITHUB_TOKEN"],
    )

    repo = client.repos.get()

    errors = {}
    try:
        assert_values(repo, project_settings.get("repo", {}), "repo")
    except SettingsMismatchError as ex:
        errors = errors | ex.mismatches

    actions_settings = project_settings.get("actions", {})
    try:
        assert_values(
            client.actions.get_github_actions_permissions_repository(),
            actions_settings.get("actions_permissions", {}),
            name="actions.actions_permissions",
        )
    except SettingsMismatchError as ex:
        errors = errors | ex.mismatches
    try:
        assert_values(
            client.actions.get_github_actions_default_workflow_permissions_repository(),
            actions_settings.get("workflow_permissions", {}),
            name="actions.workflow_permissions",
        )
    except SettingsMismatchError as ex:
        errors = errors | ex.mismatches

    protection_settings = project_settings.get("protection", {})
    for branch_name, branch_protection in protection_settings.get(
        "branches", {}
    ).items():
        try:
            branch = client.repos.get_branch_protection(branch=branch_name)
            assert_values(
                branch, branch_protection, f"branch.{{{branch_name}}}.protection"
            )
        except SettingsMismatchError as ex:
            errors = errors | ex.mismatches
        except Exception:
            errors[f"branch.{{{branch_name}}}.protection"] = {
                "current": "Unprotected",
                "desired": "Protected",
            }

    repo_tag_protections = client.repos.list_tag_protection()
    repo_tag_protections = [val["pattern"] for val in repo_tag_protections]
    try:
        assert_in_array(
            repo_tag_protections,
            protection_settings.get("tags", []),
            name="tags.protection",
        )
    except SettingsMismatchError as ex:
        errors = errors | ex.mismatches

    if errors:
        logger.error(f"Invalid settings for repository '{repo_name}'")
        for k in sorted(errors.keys()):
            logger.error(
                f"     {k} should be {errors[k]['desired']} (currently {errors[k]['current']})"
            )

    sys.exit(
        0
        if os.environ.get("INPUT_IGNORE_FAILURES", "false").lower() == "true"
        else len(errors)
    )
