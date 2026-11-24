"""Focused tests for edge cases the fixture corpus does not cover."""

import pytest

from shipshape.checks.correctness import GroupedSplitLeakage, SwallowedException
from shipshape.checks.readability import PrintDebugging, is_restating
from shipshape.checks.reproducibility import MissingSeed, UnpinnedDependencies
from shipshape.checks.security import EnvFileNotIgnored, HardcodedSecret, _gitignore_covers
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
    secret = "Zx9vQ2mL7pR4tY8wK3nB6cD1"
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
