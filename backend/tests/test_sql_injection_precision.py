"""
Phase G / S2 — the SQL Injection detectors must match SQL SHAPE, not a word.

Measured defect: both detectors substring-matched a bare verb list.

    visit_JoinedStr:  any f-string whose literal text contains
                      select | insert | update | delete
    visit_BinOp:      any `<str constant> + x` whose constant contains one

So English prose was reported as SQL injection at severity High:

    f"Failed to delete {name}"        -> High SQL Injection
    f"About to update {n} records"    -> High SQL Injection
    log("Deleted user: " + name)      -> High SQL Injection

A bare verb is not a query. The gate is now the shape of an actual SQL
statement -- `select ... from`, `insert into`, `update ... set`,
`delete from`, and the DDL forms -- plus a dynamic part, since a fully
constant string cannot carry an injection.

The constant chunks of an f-string are joined before matching, so a query
split across interpolations (`f"SELECT {cols} FROM {tbl}"`) still matches.

Deliberately NOT gated on reaching a cursor/execute sink. The corpus fixture
f2_security_injection builds the query on one line and executes it on the
next; requiring sink adjacency would trade this false-positive class for a
false-negative one. See docs/DECISIONS.md.
"""

import pytest

from backend.app.services.security_analyzer import detect_security_issues


def _sql_findings(code):
    issues = detect_security_issues(code, is_test_file=False, file_path="app.py")
    return [i for i in issues if "SQL" in str(i.get("type", ""))]


# ----------------------------------------------------------
# Prose that merely contains a SQL verb -- the FP class
# ----------------------------------------------------------

def test_fstring_prose_containing_delete_is_not_sql_injection():
    code = 'def f(name):\n    logger.info(f"Failed to delete {name}")\n'

    assert _sql_findings(code) == []


def test_fstring_prose_containing_update_is_not_sql_injection():
    code = 'def f(n):\n    print(f"About to update {n} records")\n'

    assert _sql_findings(code) == []


def test_fstring_prose_containing_select_is_not_sql_injection():
    code = 'def f(x):\n    print(f"Select a file to insert {x}")\n'

    assert _sql_findings(code) == []


def test_concatenated_prose_containing_delete_is_not_sql_injection():
    code = 'def f(n):\n    log("Deleted user: " + n)\n'

    assert _sql_findings(code) == []


def test_concatenated_prose_containing_select_is_not_sql_injection():
    code = 'def f(p):\n    show("Please select an option: " + p)\n'

    assert _sql_findings(code) == []


# ----------------------------------------------------------
# A constant string cannot carry an injection
# ----------------------------------------------------------

def test_fstring_with_no_interpolation_is_not_sql_injection():
    code = 'q = f"SELECT * FROM users"\n'

    assert _sql_findings(code) == []


def test_concatenation_of_two_constants_is_not_sql_injection():
    code = 'q = "SELECT * FROM users " + "WHERE active = 1"\n'

    assert _sql_findings(code) == []


# ----------------------------------------------------------
# Real queries -- must NOT go silent
# ----------------------------------------------------------

def test_select_fstring_is_still_reported():
    code = 'def f(uid):\n    cursor.execute(f"SELECT * FROM users WHERE id = {uid}")\n'

    assert len(_sql_findings(code)) == 1


def test_delete_from_fstring_is_still_reported():
    code = 'def f(uid):\n    cursor.execute(f"DELETE FROM users WHERE id = {uid}")\n'

    assert len(_sql_findings(code)) == 1


def test_update_set_fstring_is_still_reported():
    code = 'def f(n):\n    cursor.execute(f"UPDATE users SET name = \'{n}\'")\n'

    assert len(_sql_findings(code)) == 1


def test_insert_into_fstring_is_still_reported():
    code = 'def f(v):\n    cursor.execute(f"INSERT INTO users VALUES ({v})")\n'

    assert len(_sql_findings(code)) == 1


def test_select_concatenation_is_still_reported():
    code = 'def f(uid):\n    cursor.execute("SELECT * FROM users WHERE id = " + uid)\n'

    assert len(_sql_findings(code)) == 1


def test_query_assigned_then_executed_is_still_reported():
    """The corpus fixture's shape: built on one line, executed on the next."""
    code = (
        'def fetch_user(db, uid):\n'
        '    q = "SELECT * FROM users WHERE id = " + uid\n'
        '    return db.execute(q)\n'
    )

    assert len(_sql_findings(code)) == 1


def test_query_split_across_interpolations_is_still_reported():
    """`select` and `from` live in different constant chunks of the f-string."""
    code = 'def f(cols, tbl, v):\n    cursor.execute(f"SELECT {cols} FROM {tbl} WHERE x = {v}")\n'

    assert len(_sql_findings(code)) == 1


def test_parameterized_query_is_not_reported():
    """The labelled decoy -- placeholders, no interpolation."""
    code = 'def f(db, uid):\n    return db.execute("SELECT * FROM users WHERE id = %s", (uid,))\n'

    assert _sql_findings(code) == []
