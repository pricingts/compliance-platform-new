"""Tests for config/constants.py -- verify all constants are defined and typed."""


class TestConstants:
    def test_comerciales_is_nonempty_list(self):
        from config.constants import COMERCIALES

        assert isinstance(COMERCIALES, list)
        assert len(COMERCIALES) >= 7

    def test_terminales_has_known_ports(self):
        from config.constants import TERMINALES

        assert "Buenaventura" in TERMINALES
        assert "Cartagena" in TERMINALES
        assert isinstance(TERMINALES["Buenaventura"], list)

    def test_trading_countries_is_list(self):
        from config.constants import TRADING_COUNTRIES

        assert isinstance(TRADING_COUNTRIES, list)
        assert "Colombia" in TRADING_COUNTRIES

    def test_doc_type_mappings_has_profiles(self):
        from config.constants import DOC_TYPE_MAPPINGS

        assert 1 in DOC_TYPE_MAPPINGS
        assert 2 in DOC_TYPE_MAPPINGS
        assert "empresa" in DOC_TYPE_MAPPINGS[1]

    def test_max_upload_size(self):
        from config.constants import MAX_UPLOAD_FILE_SIZE_BYTES

        assert MAX_UPLOAD_FILE_SIZE_BYTES == 10 * 1024 * 1024
