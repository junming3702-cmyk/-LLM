import unittest
from assessment import strict_json
class StrictFinalChannelTests(unittest.TestCase):
 def test_complete_object(self):self.assertEqual(strict_json('{"a":1}'),{'a':1})
 def test_duplicate_rejected(self):
  with self.assertRaises(ValueError):strict_json('{"a":1,"a":2}')
 def test_reasoning_or_fenced_fragment_rejected(self):
  for text in ['reasoning {"a":1}','```json\n{"a":1}\n```','{"a":1} trailing']:
   with self.assertRaises(ValueError):strict_json(text)
 def test_nan_rejected(self):
  with self.assertRaises(ValueError):strict_json('{"a":NaN}')
 def test_no_fields_added_or_changed(self):
  obj=strict_json('{"finding":null,"gap":"unknown","status":" U "}')
  self.assertEqual(obj,{'finding':None,'gap':'unknown','status':' U '})
if __name__=='__main__':unittest.main()
