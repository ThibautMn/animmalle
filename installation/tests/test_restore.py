"""Vérifier la conversion sans exécuter de SQL historique."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from restore import convert_materials, head_revisions, statements, values, validate


class ConversionTests(unittest.TestCase):
    def test_escapes_unicode_null_and_empty(self):
        self.assertEqual(values(r"(1,'été; -- /* texte */','l\'outil','a\\b','x\ny','',NULL), (2,'l''outil')"),
                         [[1, 'été; -- /* texte */', "l'outil", 'a\\b', 'x\ny', '', None], [2, "l'outil"]])

    def test_comments_and_quoted_semicolon(self):
        self.assertEqual(list(statements("-- commentaire\n/*!40101 SET NAMES utf8 */; INSERT INTO `x` VALUES ('a; b');")),
                         ["INSERT INTO `x` VALUES ('a; b')"])

    def test_target_revision_is_the_latest_migration(self):
        heads = head_revisions()
        self.assertEqual(len(heads), 1)
        versions = Path(__file__).resolve().parents[2] / 'backend' / 'migrations' / 'versions'
        self.assertTrue(any(heads[0] in path.read_text(encoding='utf-8') for path in versions.glob('*.py')))

    def test_invalid_inputs_are_rejected(self):
        for source in ["(1, NOW())", "('incomplet)", '(1),', '(0xFF)', '(1) DELETE']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                values(source)
        for source in ["INSERT ('incomplet);", '/* incomplet', "/*! SET SQL_MODE='NO_BACKSLASH_ESCAPES' */;"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                list(statements(source))

    def test_mat_peda_is_split_into_media_and_tools(self):
        row = dict(nom='n', description='', url='', localisation='', variante='', difficulte_id=None,
                   materiel='', date_modif=None, fk_type_mat_outil_id=None)
        tables = {'thesaurus': [dict(id=1, reference='ref.type_mat'), dict(id=2, reference='ref.type_outil')],
                  'mat_peda': [dict(row, id=10, fk_type_mat_id=1, fk_type_mat_outil_id=1),
                               dict(row, id=11, fk_type_mat_id=2, difficulte_id=3, variante='v')],
                  'rel_mat_peda_sequence': [dict(id=1, fk_mat_peda_id=10, fk_sequence_id=4)],
                  'rel_mat_peda_thematique': [dict(id=2, fk_mat_peda_id=10, fk_thes_id=1)]}
        next_ids = {'mat_peda': 12, 'rel_mat_peda_sequence': 2}
        convert_materials(tables, next_ids)
        self.assertEqual([r['id'] for r in tables['media']], [10])
        self.assertEqual(set(tables['media'][0]), {'id', 'fk_type_mat_id', 'nom', 'description', 'url', 'date_modif'})
        self.assertEqual(tables['outil_facilitateur'][0]['fk_type_outil_id'], 2)
        self.assertEqual(tables['outil_facilitateur'][0]['difficulte_id'], 3)
        self.assertEqual(tables['rel_media_sequence'], [dict(id=1, fk_media_id=10, fk_sequence_id=4)])
        self.assertNotIn('mat_peda', tables)
        self.assertEqual((next_ids['media'], next_ids['outil_facilitateur'], next_ids['rel_media_sequence']), (12, 12, 2))
        tables['rel_mat_peda_sequence'] = [dict(id=1, fk_mat_peda_id=11, fk_sequence_id=4)]
        tables.update(mat_peda=[dict(row, id=11, fk_type_mat_id=2)], rel_mat_peda_thematique=[])
        with self.assertRaisesRegex(ValueError, 'outil'):
            convert_materials(tables, {})

    def test_duplicate_and_orphan_rejected(self):
        from animmalle.models import Base
        tables = {name: [] for name in Base.metadata.tables}
        tables['thesaurus'] = [dict(id=1, label='a', code='', reference='', position=0)] * 2
        with self.assertRaisesRegex(ValueError, 'dupliquée'):
            validate(tables)
        tables['thesaurus'] = []
        tables['rel_anim_tag'] = [dict(id=1, fk_anim_id='absente', fk_thes_id=1)]
        with self.assertRaisesRegex(ValueError, 'orpheline'):
            validate(tables)
