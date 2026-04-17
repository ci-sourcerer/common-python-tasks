from unittest.mock import patch


def test_build_with_containers_calls_task_build_image():
    from common_python_tasks.docker import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(
            has_containers=True,
            debug=True,
            no_cache=True,
            plain=True,
            single_arch=True,
        )

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_called_once_with(
        debug=True,
        no_cache=True,
        plain=True,
        single_arch=True,
        build_args=None,
        container_env=None,
        container_envfile=None,
    )


def test_build_forwards_container_build_options():
    from common_python_tasks.docker import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(
            has_containers=True,
            debug=True,
            no_cache=True,
            plain=True,
            single_arch=True,
            build_args=["FOO=bar"],
            container_env=["X=1"],
            container_envfile=["env1.env", "env2.env"],
        )

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_called_once_with(
        debug=True,
        no_cache=True,
        plain=True,
        single_arch=True,
        build_args=["FOO=bar"],
        container_env=["X=1"],
        container_envfile=["env1.env", "env2.env"],
    )


def test_build_without_containers_skips_task_build_image():
    from common_python_tasks.docker import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(has_containers=False)

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_not_called()
