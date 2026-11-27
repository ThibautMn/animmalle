import unittest

from animmalle.kit import QUOTE_CLOSE, QUOTE_OPEN, RichConverter


def convert(html):
    converter = RichConverter()
    converter.feed(html)
    converter.close()
    return converter.result()


class CitationTests(unittest.TestCase):
    def test_quotes_wrap_whole_blockquote(self):
        xml = convert('<p>Avant</p><blockquote><p>Un</p><p>Deux</p></blockquote><p>Après</p>')
        self.assertEqual(xml.count(QUOTE_OPEN), 1)
        self.assertEqual(xml.count(QUOTE_CLOSE), 1)
        self.assertIn(f'<text:p text:style-name="Citation">{QUOTE_OPEN}Un</text:p>', xml)
        self.assertIn(f'<text:p text:style-name="Citation">Deux{QUOTE_CLOSE}</text:p>', xml)
        self.assertIn('<text:p text:style-name="Corps">Après</text:p>', xml)

    def test_empty_blockquote_has_no_quotes(self):
        xml = convert('<blockquote></blockquote><p>x</p>')
        self.assertNotIn('Guillemet', xml)
        self.assertEqual(xml, '<text:p text:style-name="Corps">x</text:p>')


if __name__ == '__main__':
    unittest.main()
