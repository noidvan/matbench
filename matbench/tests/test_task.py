import unittest
import random
import json
import copy
import os
import glob

import pandas as pd
import numpy as np
from pymatgen import Structure

from matbench.task import MatbenchTask
from matbench.metadata import mbv01_metadata, mbv01_validation
from matbench.constants import CLF_KEY, REG_KEY, PARAMS_KEY, DATA_KEY, SCORES_KEY, FOLD_DIST_METRICS, REG_METRICS, CLF_METRICS, COMPOSITION_KEY, STRUCTURE_KEY, MBV01_KEY, TEST_KEY


TEST_DIR = os.path.dirname(os.path.abspath(__file__))


def model_random(training_outputs, test_inputs, response_type, seed):
    r = random.Random(seed)

    l = len(test_inputs)

    if response_type == CLF_KEY:
        return r.choices([True, False], k=l)

    # Regression: simply sample from random distribution bounded by max and min training samples
    pred = [None] * l
    if response_type == REG_KEY:
        for i in range(l):
            pred[i] = r.uniform(max(training_outputs), min(training_outputs))
        return pred


class TestMatbenchTask(unittest.TestCase):
    test_datasets = ["matbench_dielectric", "matbench_steels", "matbench_glass"]

    def setUp(self) -> None:
        self.shuffle_seed = 1001

    def tearDown(self) -> None:
        # remove all temporary output files
        for f in glob.glob(os.path.join(TEST_DIR, "*_output.json")):
            os.remove(f)

    def test_instantiation(self):
        for ds in self.test_datasets:
            mbt = MatbenchTask(ds, autoload=True)

    def test_get_train_and_val_data(self):
        # Assuming 5-fold nested cross validation
        for ds in self.test_datasets:
            mbt = MatbenchTask(ds, autoload=True)
            mbt.load()
            # shuffle seed must be set because it shuffles the (same) training data in a deterministic manner
            inputs, outputs = mbt.get_train_and_val_data(fold_number=0, as_type="tuple", shuffle_seed=self.shuffle_seed)


            self.assertListEqual(inputs.index.tolist(), outputs.index.tolist())
            self.assertEqual(inputs.shape[0], int(np.floor(mbt.df.shape[0] * 4/5)))
            self.assertEqual(outputs.shape[0], int(np.floor(mbt.df.shape[0] * 4/5)))

            input_type = Structure if mbt.metadata.input_type == STRUCTURE_KEY else str
            output_type = float if mbt.metadata.task_type == REG_KEY else bool
            self.assertTrue(all([isinstance(d, input_type) for d in inputs]))
            self.assertTrue(all([isinstance(d, output_type) for d in outputs]))

            if ds == "matbench_dielectric":
                mat = inputs.loc["mb-dielectric-1985"]
                f = mat.composition.reduced_formula
                val = outputs.loc["mb-dielectric-1985"]
                self.assertEqual(f, "Re3(TeBr)7")
                self.assertEqual(inputs.iloc[0], mat)    # ensure the ordering is correct via iloc
                n = 2.5230272821931656
                self.assertAlmostEqual(val, n, places=10)
                self.assertAlmostEqual(outputs.iloc[0], n, places=10)
            elif ds == "matbench_steels":
                alloy = "Fe0.692C0.00968Mn0.000101Si0.0144Cr0.133Ni0.00887Mo0.0114V0.000109Nb0.000477Co0.130Al0.000616"
                mat = inputs.loc["mb-steels-095"]
                val = outputs.loc["mb-steels-095"]
                self.assertEqual(alloy, mat)
                self.assertEqual(alloy, inputs.iloc[55])
                yield_strength = 1369.5
                self.assertAlmostEqual(val, yield_strength, places=5)
                self.assertAlmostEqual(outputs.iloc[55], yield_strength, places=5)
            elif ds == "matbench_glass":
                alloy = "Ce2Al5Cu43"
                mat = inputs.loc["mb-glass-0600"]
                val = outputs.loc["mb-glass-0600"]
                self.assertEqual(alloy, mat)
                self.assertEqual(alloy, inputs.iloc[-1])
                gfa = False
                self.assertEqual(val, gfa)
                self.assertEqual(outputs.iloc[-1], gfa)

    def test_get_test_data(self):
        for ds in self.test_datasets:
            mbt = MatbenchTask(ds, autoload=False)
            mbt.load()
            folds = []
            for fold in mbt.folds:
                inputs, outputs = mbt.get_test_data(fold_number=fold, as_type="tuple", include_target=True)

                self.assertListEqual(inputs.index.tolist(), outputs.index.tolist())

                upper_bound = int(np.ceil(mbt.df.shape[0]/5))
                allowed_fold_sizes = (upper_bound - 1, upper_bound)
                self.assertTrue(inputs.shape[0] in allowed_fold_sizes)
                self.assertTrue(outputs.shape[0] in allowed_fold_sizes)
                input_type = Structure if mbt.metadata.input_type == STRUCTURE_KEY else str
                output_type = float if mbt.metadata.task_type == REG_KEY else bool
                self.assertTrue(all([isinstance(d, input_type) for d in inputs]))
                self.assertTrue(all([isinstance(d, output_type) for d in outputs]))
                folds.append((inputs, outputs))

            # check if all entries from original df are in exactly one test fold exactly once
            original_input_df = mbt.df[mbt.metadata.input_type]
            inputs_from_folds = pd.concat([f[0] for f in folds])
            self.assertEqual(inputs_from_folds.shape[0], original_input_df.shape[0])
            self.assertTrue(original_input_df.apply(lambda i: i in inputs_from_folds.tolist()).all())


            # Test individual samples from an individual test set
            inputs, outputs = folds[0]
            if ds == "matbench_dielectric":
                ki = inputs.iloc[12].composition.reduced_formula
                self.assertEqual(ki, "KI")
                self.assertEqual(ki, inputs.loc["mb-dielectric-0076"].composition.reduced_formula)
                self.assertEqual(ki, mbt.df[STRUCTURE_KEY].loc["mb-dielectric-0076"].composition.reduced_formula)
                n = 1.7655027612552967
                self.assertAlmostEqual(outputs.iloc[12], n, places=10)
                self.assertAlmostEqual(outputs.loc["mb-dielectric-0076"], n, places=10)
                self.assertAlmostEqual(mbt.df[mbt.metadata.target].loc["mb-dielectric-0076"], n, places=10)
            elif ds == "matbench_steels":
                alloy = "Fe0.682C0.00877Mn0.000202Si0.00967Cr0.134Ni0.00907Mo0.00861V0.00501Nb0.0000597Co0.142Al0.000616"
                self.assertEqual(alloy, inputs.loc["mb-steels-068"])
                self.assertEqual(alloy, inputs.iloc[12])
                self.assertEqual(alloy, mbt.df[COMPOSITION_KEY].loc["mb-steels-068"])
                yield_strength = 1241.0
                self.assertAlmostEqual(outputs.iloc[12], yield_strength, places=5)
                self.assertAlmostEqual(outputs.loc["mb-steels-068"], yield_strength, places=5)
                self.assertAlmostEqual(mbt.df[mbt.metadata.target].loc["mb-steels-068"], yield_strength, places=5)
            elif ds == "matbench_glass":
                alloy = "Al13VCu6"
                self.assertEqual(alloy, inputs.iloc[12])
                self.assertEqual(alloy, inputs.loc["mb-glass-0056"])
                self.assertEqual(alloy, mbt.df[COMPOSITION_KEY].loc["mb-glass-0056"])
                gfa = True
                self.assertEqual(outputs.iloc[12], gfa)
                self.assertEqual(outputs.loc["mb-glass-0056"], gfa)
                self.assertEqual(mbt.df[mbt.metadata.target].loc["mb-glass-0056"], gfa)

    def test_get_task_info(self):
        mbt = MatbenchTask("matbench_steels", autoload=False)
        mbt.get_task_info()
        self.assertTrue("citations" in mbt.info.lower())
        self.assertTrue("SHA256 Hash Digest" in mbt.info)

    def test_record(self):
        for ds in self.test_datasets:
            # Testing two scenarios: model is perfect, and model is random
            for model_is_perfect in (True, False):
                mbt = MatbenchTask(ds, autoload=False)
                mbt.load()

                # test to make sure raw data output is correct, using a random model
                for fold, fold_key in mbt.folds_map.items():
                    _, training_outputs = mbt.get_train_and_val_data(fold, as_type="tuple", shuffle_seed=self.shuffle_seed)
                    if model_is_perfect:
                        test_inputs, test_outputs = mbt.get_test_data(fold, as_type="tuple", include_target=True)
                        model_response = test_outputs
                    else:
                        test_inputs = mbt.get_test_data(fold, as_type="tuple",include_target=False)
                        model_response = model_random(training_outputs, test_inputs, response_type=mbt.metadata.task_type, seed=self.shuffle_seed)
                    mbt.record(fold, predictions=model_response, params={"test_param": 1, "other_param": "string", "hyperparam": True})
                    self.assertEqual(len(mbt.results[fold_key].data.values()), len(test_inputs))
                    self.assertEqual(mbt.results[fold_key].parameters.test_param, 1)
                    self.assertEqual(mbt.results[fold_key].parameters.other_param, "string")
                    self.assertEqual(mbt.results[fold_key].parameters.hyperparam, True)

                if ds == "matbench_dielectric":
                    mae = mbt.results.fold_0.scores.mae
                    val = mbt.results.fold_0.data["mb-dielectric-0008"]
                    if model_is_perfect:
                        self.assertAlmostEqual(mae, 0.0, places=10)
                        self.assertAlmostEqual(val, 2.0323401126123875, places=10)
                    else:
                        self.assertAlmostEqual(mae, 28.67286016140617, places=10)
                        self.assertAlmostEqual(val, 13.417101448163713, places=10)
                elif ds == "matbench_steels":
                    mae = mbt.results.fold_0.scores.mae
                    if model_is_perfect:
                        self.assertAlmostEqual(mae, 0.0, places=10)
                    else:
                        self.assertAlmostEqual(mae, 503.00317490820277, places=10)
                elif ds == "matbench_glass":
                    rocauc = mbt.results.fold_0.scores.rocauc
                    if model_is_perfect:
                        self.assertAlmostEqual(rocauc, 1.0, places=10)
                    else:
                        self.assertAlmostEqual(rocauc, 0.5061317574566012, places=10)

                self.assertTrue(mbt.all_folds_recorded)

                with self.assertRaises(ValueError):
                    mbt.record(0, predictions=np.random.random(mbt.metadata.n_samples))

            mbt = MatbenchTask(self.test_datasets[0], autoload=True)
            # Test to make sure bad predictions won't be recorded
            with self.assertRaises(ValueError):
                mbt.record(0, [0.0, 1.0])

            with self.assertRaises(ValueError):
                mbt.record(0, ["not", "a number"])

    def test_MSONability(self):
        for ds in self.test_datasets:
            mbt = MatbenchTask(ds, autoload=False)
            mbt.load()

            for fold in mbt.folds:
                _, training_outputs = mbt.get_train_and_val_data(fold, as_type="tuple", shuffle_seed=self.shuffle_seed)
                test_inputs, test_outputs = mbt.get_test_data(fold, as_type="tuple", include_target=True)
                mbt.record(fold, predictions=test_outputs, params={"some_param": 1, "another param": 30349.4584})

            d = mbt.as_dict()

            self.assertEqual(d["@module"], "matbench.task")
            self.assertEqual(d["@class"], "MatbenchTask")
            self.assertEqual(d[mbt.BENCHMARK_KEY], MBV01_KEY)
            self.assertEqual(d[mbt.DATASET_KEY], ds)
            self.assertEqual(len(d["results"]), len(mbt.validation.keys()))

            for fold, fold_key in mbt.folds_map.items():
                res = d["results"][fold_key]
                self.assertIn(PARAMS_KEY, res)
                self.assertIn(SCORES_KEY, res)
                self.assertIn(DATA_KEY, res)

                # make sure test set as per MbT and the recorded predictions are the same shape inside dict
                self.assertEqual(len(res["data"]), len(mbt.validation[fold_key][TEST_KEY]))

            mbt.to_file(os.path.join(TEST_DIR, f"msonability_{ds}_output.json"))

            # todo: uncomment to regenerate test files
            # todo: these can be used as the score_matbench_*_perfect.json files as well if renamed.
            mbt.to_file(os.path.join(TEST_DIR, f"msonability_{ds}.json"))


            # # Test ingestion from ground truth json files
            # truth_fname = f"msonability_{ds}.json"
            #
            # with open(truth_fname, "r") as f:
            #     truth = json.load(f)
            # MatbenchTask.from_file(truth_fname)
            # MatbenchTask.from_dict(truth)
            #
            #
            # # Ensure errors are thrown for bad json
            #
            # missing_results = copy.deepcopy(truth)
            # missing_results.pop("results")
            #
            # with self.assertRaises(KeyError):
            #     MatbenchTask.from_dict(missing_results)
            #
            # for key in [PARAMS_KEY, DATA_KEY, SCORES_KEY]:
            #     missing_key = copy.deepcopy(truth)
            #     missing_key["results"]["fold_3"].pop(key)
            #
            #     with self.assertRaises(KeyError):
            #         MatbenchTask.from_dict(missing_key)
            #
            # # If an otherwise perfect json is missing a required index
            # missing_ix_fold0 = copy.deepcopy(truth)
            # missing_ix_fold0["results"]["fold_0"]["data"].pop(mbt.split_ix[0][1][0])
            #
            # with self.assertRaises(ValueError):
            #     MatbenchTask.from_dict(missing_ix_fold0)
            #
            # # If an otherwise perfect json has an extra index
            # extra_ix_fold0 = copy.deepcopy(truth)
            # extra_ix_fold0["results"]["fold_0"]["data"][310131] = 1.92
            #
            # with self.assertRaises(ValueError):
            #     MatbenchTask.from_dict(extra_ix_fold0)
            #
            # # If an otherwise perfect json has a wrong datatype
            # wrong_dtype = copy.deepcopy(truth)
            # wrong_dtype["results"]["fold_2"]["data"][mbt.split_ix[2][1][4]] = "any string"
            #
            # with self.assertRaises(TypeError):
            #     MatbenchTask.from_dict(wrong_dtype)

    def test_autoload(self):
        mbt = MatbenchTask("matbench_steels", autoload=False)
        with self.assertRaises(ValueError):
            mbt._check_is_loaded()

        with self.assertRaises(ValueError):
            mbt.get_test_data(0)

        with self.assertRaises(ValueError):
            mbt.get_train_and_val_data(0)

        mbt.load()
        mbt._check_is_loaded()
        mbt.get_test_data(0)
        mbt.get_train_and_val_data(0)

        MatbenchTask("matbench_steels", autoload=True)

    def test_scores(self):
        mbt = MatbenchTask.from_file("scores_matbench_dielectric_perfect.json")

        for metric in REG_METRICS:
            for fdm in FOLD_DIST_METRICS:
                self.assertAlmostEqual(0.0, mbt.scores[metric][fdm], places=10)

        mbt = MatbenchTask.from_file("scores_matbench_glass_perfect.json")

        for metric in CLF_METRICS:
            for fdm in FOLD_DIST_METRICS:
                test_val = 0.0 if fdm == "std" else 1.0
                self.assertAlmostEqual(test_val, mbt.scores[metric][fdm], places=10)

    def test_usage(self):
        # access some common attrs
        mbt_clf = MatbenchTask.from_file("scores_matbench_dielectric_perfect.json")
        mbt_reg = MatbenchTask.from_file("scores_matbench_glass_perfect.json")

        for mbt in (mbt_clf, mbt_reg):
            for index, datum in mbt.results.fold_2.data.items():
                self.assertTrue(isinstance(datum, (bool, float)))
                self.assertTrue(isinstance(index, int))

        self.assertTrue(isinstance(mbt.results.fold_3.parameters, (dict, type(None))))