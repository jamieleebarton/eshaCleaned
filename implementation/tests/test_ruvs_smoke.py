def test_ruvs_package_importable():
    import ruvs
    assert hasattr(ruvs, "__version__")
