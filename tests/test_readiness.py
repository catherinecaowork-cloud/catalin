from autotest_executor.browser.readiness import same_navigation_url


def test_same_navigation_url_ignores_trailing_slash() -> None:
    assert same_navigation_url(
        "https://demo.example/app/",
        "https://demo.example/app",
    )


def test_same_navigation_url_keeps_hash_query_and_host() -> None:
    assert not same_navigation_url(
        "https://demo.example/app#/home",
        "https://demo.example/app#/style",
    )
    assert not same_navigation_url(
        "https://demo.example/app?tab=1",
        "https://demo.example/app",
    )
    assert not same_navigation_url(
        "https://a.example/app",
        "https://b.example/app",
    )
