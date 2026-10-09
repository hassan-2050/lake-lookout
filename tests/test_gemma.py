from lookout.gemma import drop_echo_translation


def test_english_echo_is_dropped():
    t = ("Thorgokialake. The water is bright turquoise.\n"
         "English: Thorgokialake. The water is bright turquoise.")
    assert drop_echo_translation(t) == "Thorgokialake. The water is bright turquoise."


def test_real_translation_is_kept():
    t = "पानी खैरो थियो।\nEnglish: The water was grey."
    assert drop_echo_translation(t) == t


def test_text_without_translation_is_untouched():
    assert drop_echo_translation("Grey milky lake.") == "Grey milky lake."
