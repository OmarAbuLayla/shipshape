"""Focused tests for edge cases the fixture corpus does not cover."""

import pytest

from shipshape.checks.copies import CopiedFiles, DuplicatedPackage
from shipshape.checks.correctness import GroupedSplitLeakage, SwallowedException
from shipshape.checks.data_handling import ArrayNoneComparison, SilentDataSkip
from shipshape.checks.readability import PrintDebugging, is_restating
from shipshape.checks.reproducibility import (
    BrokenLocalImport,
    HardcodedPath,
    MissingSeed,
    UnpinnedDependencies,
)
from shipshape.checks.ruff import RuffCheck
from shipshape.checks.security import EnvFileNotIgnored, HardcodedSecret, _gitignore_covers
from shipshape.checks.structure import UnusedModule
from shipshape.checks.testing import UntestedModules
from shipshape.checks.training import MissingEvalMode, MissingZeroGrad, TestSetSelection
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


SCHEDULER = "".join(f"def step_{i}(lr):\n    return lr * {i}\n\n\n" for i in range(8))


def test_copied_files_across_experiment_folders(make_project: MakeProject) -> None:
    files = {
        "exp_gru/lr_scheduler.py": SCHEDULER,
        "exp_mamba/lr_scheduler.py": SCHEDULER,
        "eval/lr_scheduler_2.py": SCHEDULER + "# tuned\n",
        "exp_gru/train.py": "".join(f"def run_{i}():\n    return {i}\n\n\n" for i in range(8)),
    }
    (finding,) = CopiedFiles().run(make_project(files))
    assert {loc.path for loc in finding.locations} == {
        "exp_gru/lr_scheduler.py",
        "exp_mamba/lr_scheduler.py",
        "eval/lr_scheduler_2.py",
    }


def test_copied_packages_are_left_to_the_package_check(make_project: MakeProject) -> None:
    other = SCHEDULER.replace("step_", "warmup_").replace("lr * ", "lr + ")
    files = {"data/__init__.py": "", "data_old/__init__.py": ""}
    for pkg in ("data", "data_old"):
        files |= {f"{pkg}/a.py": SCHEDULER, f"{pkg}/b.py": other}
    assert CopiedFiles().run(make_project(files)) == []


def test_import_of_a_module_in_another_folder_is_broken(make_project: MakeProject) -> None:
    files = {
        "exp_a/main.py": "from helpers import f\nfrom model.py import *\n\nf()\n",
        "exp_a/model.py": "X = 1\n",
        "exp_b/helpers.py": "def f():\n    return 1\n",
        "exp_b/main.py": "from helpers import f\n\nf()\n",
        "shared.py": "Y = 2\n",
        "exp_c/run.py": "import shared\nimport numpy\n",
    }
    (finding,) = BrokenLocalImport().run(make_project(files))
    assert [(loc.path, loc.start_line) for loc in finding.locations] == [
        ("exp_a/main.py", 1),
        ("exp_a/main.py", 2),
    ]


def test_scripts_that_set_up_sys_path_are_trusted(make_project: MakeProject) -> None:
    files = {
        "exp_a/main.py": "import sys\nsys.path.append('../exp_b')\nfrom helpers import f\n",
        "exp_b/helpers.py": "def f():\n    return 1\n",
    }
    assert BrokenLocalImport().run(make_project(files)) == []


def test_files_with_a_byte_order_mark_are_parsed(make_project: MakeProject) -> None:
    project = make_project({"bom.py": "\ufeffimport os\n\nX = os.sep\n"})
    assert project.sources[0].tree is not None


def test_experiments_named_like_tests_are_not_tests(make_project: MakeProject) -> None:
    project = make_project(
        {
            "perturbation_test.py": "def run():\n    return 1\n",
            "test_real.py": "def test_one():\n    assert True\n",
            "tests/helpers.py": "X = 1\n",
        }
    )
    tests = {s.path: s.is_test for s in project.sources}
    assert tests == {
        "perturbation_test.py": False,
        "test_real.py": True,
        "tests/helpers.py": True,
    }


def test_path_templates_are_not_hard_coded_paths(make_project: MakeProject) -> None:
    code = (
        'def wsl(drive, rest):\n    return f"/mnt/{drive}/{rest}"\n\n\nDATA = "/mnt/d/data/x.csv"\n'
    )
    (finding,) = HardcodedPath().run(make_project({"paths.py": code}))
    assert [loc.start_line for loc in finding.locations] == [5]


@pytest.mark.parametrize(
    "comment",
    [
        "inputs shape: (B, 1, C, 36, 36)",
        "MFSC input may arrive as (B, 1, 6, H, W)",
        "trim the first 250 samples",
    ],
)
def test_informative_comments_are_not_restating(comment: str) -> None:
    assert not is_restating(comment, "inputs = inputs.reshape(inputs.shape[0], -1)")


def test_choosing_on_validation_while_printing_test_is_fine(make_project: MakeProject) -> None:
    code = (
        "best_val = 0\n"
        "for epoch in range(10):\n"
        "    val_acc = evaluate(model, val_loader)\n"
        "    test_acc = evaluate(model, test_loader)\n"
        "    print(test_acc)\n"
        "    if val_acc > best_val:\n"
        "        best_val = val_acc\n"
    )
    assert TestSetSelection().run(make_project({"train.py": code})) == []


def test_test_set_as_eval_set_is_selection(make_project: MakeProject) -> None:
    code = "model.fit(X_train, y_train, eval_set=[(X_test, y_test)], early_stopping_rounds=10)\n"
    (finding,) = TestSetSelection().run(make_project({"train.py": code}))
    assert finding.locations[0].start_line == 1


def test_missing_file_errors_skipped_in_a_loop(make_project: MakeProject) -> None:
    code = (
        "for path in paths:\n"
        "    try:\n"
        "        rows.append(load(path))\n"
        "    except FileNotFoundError:\n"
        "        continue\n"
        "for path in paths:\n"
        "    if not path.exists():  # optional recordings, see README\n"
        "        continue\n"
    )
    (finding,) = SilentDataSkip().run(make_project({"load.py": code}))
    assert [loc.start_line for loc in finding.locations] == [4]


def test_zero_grad_before_the_loop_is_not_enough(make_project: MakeProject) -> None:
    code = (
        "optimizer.zero_grad()\n"
        "for x, y in loader:\n"
        "    loss_fn(model(x), y).backward()\n"
        "    optimizer.step()\n"
    )
    (finding,) = MissingZeroGrad().run(make_project({"train.py": code}))
    assert finding.locations[0].start_line == 2


def test_eval_mode_in_another_file_is_not_checked(make_project: MakeProject) -> None:
    files = {
        "train.py": "for x, y in loader:\n    opt.zero_grad()\n    loss(x, y).backward()\n",
        "evaluate.py": "import torch\n\nwith torch.no_grad():\n    score = model(x)\n",
    }
    assert MissingEvalMode().run(make_project(files)) == []
