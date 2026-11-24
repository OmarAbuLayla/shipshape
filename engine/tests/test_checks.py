"""Focused tests for edge cases the fixture corpus does not cover."""

import pytest

from shipshape.checks.correctness import (
    ArrayNoneComparison,
    GroupedSplitLeakage,
    SwallowedException,
)
from shipshape.checks.readability import PrintDebugging, is_restating
from shipshape.checks.reproducibility import MissingSeed, UnpinnedDependencies
from shipshape.checks.ruff import RuffCheck
from shipshape.checks.security import EnvFileNotIgnored, HardcodedSecret, _gitignore_covers
from shipshape.checks.structure import DuplicatedPackage, UnusedModule
from shipshape.checks.testing import UntestedModules
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.scoring import dimension_scores, overall_grade

from .conftest import MakeProject

SPLIT_WITH_SUBJECTS = (
    "from sklearn.model_selection import train_test_split\n"
    "subjects = load()\n"
    "a, b = train_test_split(X, test_size=0.2, random_state=0)\n"
)


def test_leakage_is_flagged_when_subjects_are_in_scope(make_project: MakeProject) -> None:
    findings = GroupedSplitLeakage().run(make_project({"split.py": SPLIT_WITH_SUBJECTS}))

    assert len(findings) == 1
    assert "`subject`" in findings[0].message


def test_group_aware_split_is_not_flagged(make_project: MakeProject) -> None:
    code = SPLIT_WITH_SUBJECTS + "next(GroupKFold(5).split(X, y, groups=subjects))\n"

    assert GroupedSplitLeakage().run(make_project({"split.py": code})) == []


def test_split_without_group_variable_is_not_flagged(make_project: MakeProject) -> None:
    code = "from sklearn.model_selection import train_test_split\na = train_test_split(X)\n"

    assert GroupedSplitLeakage().run(make_project({"split.py": code})) == []


def test_explained_broad_except_is_deliberate(make_project: MakeProject) -> None:
    code = (
        "try:\n    a()\nexcept Exception:  # detached frames are harmless here\n    pass\n"
        "try:\n    b()\nexcept Exception:\n    pass\n"
    )

    findings = SwallowedException().run(make_project({"a.py": code}))

    assert [loc.start_line for loc in findings[0].locations] == [7]


def test_losses_and_activations_are_not_random_init(make_project: MakeProject) -> None:
    code = "import torch\nfrom torch import nn\nloss = nn.CrossEntropyLoss()\nact = nn.ReLU()\n"

    assert MissingSeed().run(make_project({"a.py": code})) == []


def test_prints_in_ui_folders_are_allowed(make_project: MakeProject) -> None:
    project = make_project({"pkg/ui/display.py": "print(1)\n" * 6})

    assert PrintDebugging().run(project) == []


def test_global_seed_anywhere_silences_missing_seed(make_project: MakeProject) -> None:
    project = make_project(
        {
            "a.py": "import random\nrandom.shuffle(x)\n",
            "b.py": "import torch\ntorch.manual_seed(0)\n",
        }
    )

    assert MissingSeed().run(project) == []


def test_seeded_calls_are_not_randomness_sites(make_project: MakeProject) -> None:
    code = (
        "import numpy as np\n"
        "rng = np.random.default_rng(7)\n"
        "train_test_split(X, random_state=1)\n"
        "KFold(5)\n"
    )

    assert MissingSeed().run(make_project({"a.py": code})) == []


def test_unpinned_dependencies_skip_options_and_comments(make_project: MakeProject) -> None:
    requirements = "# comment\n-r base.txt\nnumpy==2.0\npandas>=2\ntorch @ https://x/y.whl\n"

    findings = UnpinnedDependencies().run(make_project({"requirements.txt": requirements}))

    assert [loc.start_line for loc in findings[0].locations] == [4]


def test_secret_value_never_appears_in_the_finding(make_project: MakeProject) -> None:
    secret = "Zx9vQ2mL7pR4tY8wK3nB6cD1"  # shipshape: ignore[security.hardcoded-secret] fake
    project = make_project({"cfg.py": f'OPENAI_API_KEY = "{secret}"\n'})

    findings = HardcodedSecret().run(project)

    assert len(findings) == 1
    assert secret not in findings[0].model_dump_json()


@pytest.mark.parametrize(
    "value", ["your-api-key-here", "OPENAI_API_KEY", "https://example.com/token", "short1"]
)
def test_placeholders_and_names_are_not_secrets(make_project: MakeProject, value: str) -> None:
    project = make_project({"cfg.py": f'api_key = "{value}"\n'})

    assert HardcodedSecret().run(project) == []


def test_gitignore_fallback_handles_negation(make_project: MakeProject) -> None:
    project = make_project({".gitignore": ".env*\n!.env.shared\n", ".env.shared": "", ".env": ""})

    assert _gitignore_covers(project, ".env")
    assert not _gitignore_covers(project, ".env.shared")


def test_env_example_is_never_flagged(make_project: MakeProject) -> None:
    project = make_project({".env.example": "API_KEY=\n"})

    assert EnvFileNotIgnored().run(project) == []


@pytest.mark.parametrize(
    ("comment", "code", "expected"),
    [
        ("Load the json data", "data = json.load(handle)", True),
        ("Loop through all files", "for name in names:", True),
        ("Normalise the window", "window = normalise(window)", True),
        ("20-450 Hz keeps most sEMG power", "sos = butter(4, [20, 450])", False),
        ("Load the cache because the API is slow", "cache = load()", False),
        ("x = compute(y)", "z = 1", False),
    ],
)
def test_is_restating(comment: str, code: str, expected: bool) -> None:
    assert is_restating(comment, code) is expected


def test_prints_in_scripts_are_allowed(make_project: MakeProject) -> None:
    prints = "print(1)\n" * 6
    project = make_project(
        {
            "main.py": prints,
            "scripts/run_all.py": prints,
            "tool.py": "import argparse\n" + prints,
            "guarded.py": prints + "if __name__ == '__main__':\n    pass\n",
        }
    )

    assert PrintDebugging().run(project) == []


def _finding(dimension: Dimension, severity: Severity) -> Finding:
    return Finding(
        check_id="x",
        title="x",
        severity=severity,
        dimension=dimension,
        concept="x",
        message="x",
        locations=[Location(path=".")],
    )


def test_scores_and_grade() -> None:
    scores = dimension_scores(
        [
            _finding(Dimension.CORRECTNESS, Severity.CRITICAL),
            _finding(Dimension.CORRECTNESS, Severity.CRITICAL),
            _finding(Dimension.CORRECTNESS, Severity.CRITICAL),
            _finding(Dimension.TESTING, Severity.MINOR),
        ]
    )

    assert scores[Dimension.CORRECTNESS] == 0
    assert scores[Dimension.TESTING] == 95
    assert overall_grade(scores) == "B"
    assert overall_grade(dimension_scores([])) == "A"


def test_group_shuffle_split_without_seed_is_random(make_project: MakeProject) -> None:
    code = "from sklearn.model_selection import GroupShuffleSplit\nGroupShuffleSplit(n_splits=1)\n"

    findings = MissingSeed().run(make_project({"a.py": code}))

    assert len(findings) == 1


def test_methods_and_closures_are_counted_once() -> None:
    from shipshape.checks.structure import function_complexities

    code = (
        "class A:\n"
        "    def method(self, x):\n"
        "        def inner(y):\n"
        "            return y\n"
        "        return inner(x)\n"
        "def top():\n"
        "    return 1\n"
    )

    names = [name for name, *_ in function_complexities(code)]

    assert names == ["A.method", "inner", "top"]


LOADER = """import pandas as pd


def load(path):
    frame = pd.read_csv(path)
    if frame == None:
        return None
    return frame.dropna()
"""


def test_renamed_package_copy_is_found_by_content(make_project: MakeProject) -> None:
    files = {"data/__init__.py": "", "data/load.py": LOADER, "data/clean.py": "X = 1\n"}
    files |= {
        "data_old/__init__.py": "",
        "data_old/load.py": LOADER.replace("return None", "return None  # old"),
        "data_old/clean.py": "X = 1\n",
    }
    (finding,) = DuplicatedPackage().run(make_project(files))
    assert {loc.path for loc in finding.locations} == {"data", "data_old"}
    assert "different names" in finding.message


def test_different_packages_with_shared_file_names_are_not_copies(
    make_project: MakeProject,
) -> None:
    files = {
        "api/__init__.py": "",
        "api/models.py": "class User:\n    name: str\n",
        "api/utils.py": "def slug(text):\n    return text.lower()\n",
        "ml/__init__.py": "",
        "ml/models.py": "import torch\n\nNET = torch.nn.Linear(2, 1)\n",
        "ml/utils.py": "def mean(xs):\n    return sum(xs) / len(xs)\n",
    }
    assert DuplicatedPackage().run(make_project(files)) == []


def test_untested_modules_counts_small_modules_too(make_project: MakeProject) -> None:
    body = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(6))
    files = {"a.py": body, "b.py": body, "c.py": body, "tests/test_a.py": "import a\n"}
    (finding,) = UntestedModules().run(make_project(files))
    assert {loc.path for loc in finding.locations} == {"b.py", "c.py"}


def test_none_comparison_on_a_dataframe_is_a_correctness_problem(
    make_project: MakeProject,
) -> None:
    project = make_project({"load.py": LOADER, "other.py": "def f(x):\n    return x == None\n"})
    (finding,) = ArrayNoneComparison().run(project)
    assert [(loc.path, loc.start_line) for loc in finding.locations] == [("load.py", 6)]
    lint = [f for f in RuffCheck().run(project) if f.check_id == "lint.none-comparison"]
    assert [(loc.path, loc.start_line) for f in lint for loc in f.locations] == [("other.py", 2)]


def test_merged_parameter_counts_as_a_dataframe(make_project: MakeProject) -> None:
    code = (
        "def merge(visits, labs):\n"
        "    if labs == None:\n"
        "        return visits\n"
        "    return visits.merge(labs, on='id')\n"
    )
    (finding,) = ArrayNoneComparison().run(make_project({"m.py": code}))
    assert finding.locations[0].start_line == 2


def test_shuffled_indices_sliced_into_parts_are_a_split(make_project: MakeProject) -> None:
    code = (
        "import numpy as np\n"
        "patients = df['patient_id']\n"
        "idx = np.random.permutation(len(df))\n"
        "train, test = df.iloc[idx[:4000]], df.iloc[idx[4000:]]\n"
    )
    (finding,) = GroupedSplitLeakage().run(make_project({"split.py": code}))
    assert [loc.start_line for loc in finding.locations] == [4]


def test_sample_and_drop_is_a_split(make_project: MakeProject) -> None:
    code = (
        "subjects = df['subject']\n"
        "train = df.sample(frac=0.8, random_state=0)\n"
        "test = df.drop(train.index)\n"
    )
    (finding,) = GroupedSplitLeakage().run(make_project({"split.py": code}))
    assert [loc.start_line for loc in finding.locations] == [2]


def test_shuffling_without_slicing_is_not_a_split(make_project: MakeProject) -> None:
    code = (
        "import random\n"
        "patients = load()\n"
        "random.shuffle(patients)\n"
        "for p in patients:\n"
        "    show(p)\n"
    )
    assert GroupedSplitLeakage().run(make_project({"order.py": code})) == []


def test_unused_module_is_found_and_scripts_are_not(make_project: MakeProject) -> None:
    files = {
        "main.py": "from lib import helper\n\nhelper()\n",
        "lib.py": "def helper():\n    return 1\n",
        "dead.py": "def old():\n    return 2\n",
        "run_me.py": "def go():\n    return 3\n\n\nif __name__ == '__main__':\n    go()\n",
        "pkg/__init__.py": "",
        "examples/demo.py": "def demo():\n    return 4\n",
        "tests/test_lib.py": "from lib import helper\n",
    }
    (finding,) = UnusedModule().run(make_project(files))
    assert [loc.path for loc in finding.locations] == ["dead.py"]


def test_module_used_only_by_a_notebook_counts_as_used(make_project: MakeProject) -> None:
    notebook = (
        '{"cells": [{"cell_type": "code", "metadata": {}, "outputs": [], '
        '"execution_count": null, "source": ["from lib import helper\\n"]}], '
        '"metadata": {}, "nbformat": 4, "nbformat_minor": 5}'
    )
    files = {"lib.py": "def helper():\n    return 1\n", "explore.ipynb": notebook}
    assert UnusedModule().run(make_project(files)) == []


def test_installable_libraries_are_not_checked_for_unused_modules(
    make_project: MakeProject,
) -> None:
    files = {
        "pyproject.toml": "[project]\nname = 'mylib'\n",
        "mylib/__init__.py": "",
        "mylib/api.py": "def public():\n    return 1\n",
    }
    assert UnusedModule().run(make_project(files)) == []
