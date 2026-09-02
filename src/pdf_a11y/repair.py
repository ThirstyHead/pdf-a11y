"""Deterministic repair for already-tagged-but-weak structure trees.

Repairs ONLY structural-integrity defects that are mechanically resolvable:
  * orphaned structure elements (missing /P)  -> repointed to the Document root
  * ParentTree missing the root's page entry  -> rewritten consistently
Deliberately NOT repaired (fail-safe -> left as an honest residual finding):
  * content-level weaknesses (no headings, missing Alt, table without TH) and
    unbalanced BDC/EMC — these need human content and guessing is unsafe.

Reused by the Phase-C `parenttree-mcid-integrity` rule, so keep the function
pure on DocModel: no flags, no side effects beyond the tree rewrite, and it
never raises (the remediation engine records failures, not exceptions).
"""
import pikepdf

from .docmodel import key, new_dict


def _root_element(st):
    """The Document root structure element, or None.

    The root is the first entry of /K (a single element or a one-item array);
    an integer /K means the root points at a marked-content id directly —
    there is no repairable element to hang orphans on.
    """
    k = key(st, "K")
    if isinstance(k, pikepdf.Array):
        k = k[0] if k else None
    return None if (k is None or isinstance(k, int)) else k


def repair_weak_tree(dm) -> dict:
    """Repair orphaned /P pointers and the ParentTree. Never raises.

    Returns {"repointed": int, "parenttree_fixed": int, "residual": [str, ...]}.
    ``residual`` lists structural defects this function refuses to guess at
    (e.g. unbalanced BDC/EMC) so callers can report them honestly.
    """
    st = dm.struct_tree()
    if st is None:
        return {"repointed": 0, "parenttree_fixed": 0, "residual": ["no struct tree"]}
    root = _root_element(st)
    repointed = 0
    if root is not None:
        for _, _s, _alt, has_p, el in dm.walk_struct(st):
            if el is None or isinstance(el, int) or has_p:
                continue
            el["/P"] = root
            repointed += 1
    # ParentTree: ensure the page-0 entry references the root element.
    fixed = 0
    if root is not None:
        pt = key(st, "ParentTree")
        if pt is None:
            st["/ParentTree"] = new_dict(
                {"Nums": pikepdf.Array([0, pikepdf.Array([root])])})
            fixed = 1
        else:
            nums = key(pt, "Nums")
            present = False
            if isinstance(nums, pikepdf.Array):
                for i in range(0, len(nums) - 1, 2):
                    arr = nums[i + 1]
                    if isinstance(arr, pikepdf.Array) and root in arr:
                        present = True
            if not present:
                if not isinstance(nums, pikepdf.Array):
                    pt["/Nums"] = pikepdf.Array([0, pikepdf.Array([root])])
                else:
                    nums.extend(pikepdf.Array([0, pikepdf.Array([root])]))
                fixed = 1
    residual = []
    bdc, emc, _ = dm.content_bdc_counts()
    if bdc and bdc != emc:
        residual.append(f"unbalanced BDC/EMC (BDC={bdc}, EMC={emc}); manual review")
    return {"repointed": repointed, "parenttree_fixed": fixed, "residual": residual}
