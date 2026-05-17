"""Output-apply modes wrap the expression group for modifier use."""

from pathlib import Path

import pytest

from coding_nodes import plan_source
from coding_nodes.backend.plan import APPLY_MODES

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _src(name):
    return (EXAMPLES / name).read_text()


def test_raw_mode_has_no_wrapper():
    plan = plan_source(_src("ripple.py"), apply_mode="raw")
    assert plan.modifier_root_name is None
    assert plan.deliverable_root() == plan.root_name
    assert plan.apply_mode == "raw"


@pytest.mark.parametrize("mode", ["offset", "absolute"])
def test_wrapped_modes_add_a_geometry_io_group(mode):
    plan = plan_source(_src("ripple.py"), apply_mode=mode)
    assert plan.modifier_root_name is not None
    w = plan.groups[plan.modifier_root_name]
    in_types = {t for _, t in w.inputs}
    out_types = {t for _, t in w.outputs}
    assert "geometry" in in_types       # a real modifier tree
    assert out_types == {"geometry"}
    # The expression group is instantiated inside the wrapper.
    assert any(i.group_name == plan.root_name for i in w.instances)
    assert plan.deliverable_root() == plan.modifier_root_name


def test_offset_wires_result_into_set_position_offset():
    plan = plan_source(_src("ripple.py"), apply_mode="offset")
    w = plan.groups[plan.modifier_root_name]
    sp = [n for n in w.nodes if n.op == "modifier.set_position"]
    assert len(sp) == 1
    # A link from the expression instance Result into Set Position.
    assert any(l.src.kind == "instance" and l.src.socket == "Result"
               for l in w.links)
    # Geometry threads in and out.
    assert any(l.src.kind == "group_input" and l.src.socket == "Geometry"
               for l in w.links)
    assert any(l.dst.kind == "group_output" and l.dst.socket == "Geometry"
               for l in w.links)


def test_wrapper_exposes_user_parameters():
    plan = plan_source(_src("ripple.py"), apply_mode="offset")
    w = plan.groups[plan.modifier_root_name]
    names = {n for n, _ in w.inputs}
    assert {"freq", "amp"} <= names
    assert "Geometry" in names


def test_unknown_apply_mode_rejected():
    with pytest.raises(ValueError, match="unknown apply_mode"):
        plan_source(_src("ripple.py"), apply_mode="teleport")


def test_apply_modes_constant_is_the_supported_set():
    assert APPLY_MODES == ("raw", "offset", "absolute")


def test_curl_noise_wraps_too():
    plan = plan_source(_src("curl_noise.py"), apply_mode="offset",
                       inline_threshold=2)
    assert plan.modifier_root_name is not None
    # Sub-groups still present underneath the wrapper.
    assert len(plan.groups) >= 14  # wrapper + Expr_curl + 12 n_*
