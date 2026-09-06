from pathlib import Path


def _source_between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_payslip_gets_do_not_initialize_schema_or_commit() -> None:
    source = Path("api/payslip_distribution.py").read_text()
    list_source = _source_between(
        source,
        "def list_payslip_runs(",
        '@router.get("/payslips/runs/{run_id}")',
    )
    detail_source = _source_between(
        source,
        "def payslip_run_detail(",
        '@router.post("/payslips/runs/{run_id}/employees/{employee_id}/distributed")',
    )

    for get_source in (list_source, detail_source):
        assert "ensure_distribution_schema(conn)" not in get_source
        assert "ensure_adjustment_schema(conn)" not in get_source
        assert "conn.commit()" not in get_source
        assert "CREATE TABLE" not in get_source
        assert "ALTER TABLE" not in get_source


def test_distribution_write_retains_defensive_schema_initialization() -> None:
    source = Path("api/payslip_distribution.py").read_text()
    write_source = source.split("def mark_payslip_distributed(", 1)[1]
    assert "ensure_distribution_schema(conn)" in write_source
    assert "conn.commit()" in write_source


def test_runtime_startup_owns_payslip_distribution_schema() -> None:
    source = Path("api/server.py").read_text()
    assert "ensure_distribution_schema" in source
    init_source = source.split("def initialize_runtime()", 1)[1].split("@asynccontextmanager", 1)[0]
    assert "ensure_distribution_schema(conn)" in init_source
