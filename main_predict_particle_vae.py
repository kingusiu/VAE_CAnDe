import os
import setGPU
import tensorflow as tf

import pofah.util.experiment as ex
import pofah.util.event_sample as es
import vae.losses as losses
from vae.vae_particle import VAEparticle
import config.config as co
import pofah.util.sample_factory as sf
import pofah.path_constants.sample_dict_file_parts_input as sdi 
import pofah.path_constants.sample_dict_file_parts_reco as sdr 
import sarewt.data_reader as dare
import training as train


# ********************************************************
#               runtime params
# ********************************************************

test_samples = ['qcdSideExt','qcdSig', 'GtoWW15na', 'GtoWW15br', 'GtoWW25na', 'GtoWW25br', 'GtoWW35na', 'GtoWW35br', 'GtoWW45na', 'GtoWW45br']
#test_samples = ['qcdSig', 'GtoWW35na']
#test_samples = ['qcdSig']
#test_samples = ['qcdSigBis']

run_n = 7104

experiment = ex.Experiment(run_n=run_n).setup(model_dir=True)
batch_n = 1024

# ********************************************
#               load model
# ********************************************

vae = VAEparticle.from_saved_model(path=experiment.model_dir)
print('beta factor: ', vae.beta)
loss_fn = losses.threeD_loss


input_paths = sf.SamplePathDirFactory(sdi.path_dict)
result_paths = sf.SamplePathDirFactory(sdr.path_dict).update_base_path({'$run$': experiment.run_dir})

for sample_id in test_samples:

    # ********************************************
    #               read test data (events)
    # ********************************************


    list_ds = tf.data.Dataset.list_files(input_paths.sample_dir_path(sample_id)+'/*')

    for file_path in list_ds:

        file_name = file_path.numpy().decode('utf-8').split(os.sep)[-1]
        test_sample = es.EventSample.from_input_file(sample_id, file_path.numpy().decode('utf-8'))
        test_evts_j1, test_evts_j2 = test_sample.get_particles()
        print('{}: {} j1 evts, {} j2 evts'.format(file_path.numpy().decode('utf-8'), len(test_evts_j1), len(test_evts_j2)))
        test_j1_ds = tf.Dataset.from_tensor_slices(test_evts_j1).batch(batch_n, drop_remainder=True)
        test_j2_ds = tf.Dataset.from_tensor_slices(test_evts_j2).batch(batch_n, drop_remainder=True)

        # *******************************************************
        #         forward pass test data -> reco and losses
        # *******************************************************

        print('predicting {}'.format(sdi.path_dict['sample_name'][sample_id]))
        reco_j1, loss_j1_reco, loss_j1_kl = train.predict(vae.model, loss_fn, test_j1_ds)
        reco_j2, loss_j2_reco, loss_j2_kl = train.predict(vae.model, loss_fn, test_j2_ds)
        losses_j1 = [losses.total_loss(loss_j1_reco, loss_j1_kl, vae.beta), loss_j1_reco, loss_j1_kl]
        losses_j2 = [losses.total_loss(loss_j2_reco, loss_j2_kl, vae.beta), loss_j2_reco, loss_j2_kl]

        # *******************************************************
        #               add losses to DataSample and save
        # *******************************************************

        reco_sample = es.EventSample(sample_id + 'Reco', particles=[reco_j1, reco_j2], jet_features=test_sample.get_event_features(), particle_feature_names=test_sample.particle_feature_names)

        for loss, label in zip( losses_j1, ['j1TotalLoss', 'j1RecoLoss', 'j1KlLoss']):
            reco_sample.add_event_feature(label, loss)
        for loss, label in zip( losses_j2, ['j2TotalLoss', 'j2RecoLoss', 'j2KlLoss']):
            reco_sample.add_event_feature(label, loss)

        # *******************************************************
        #               write predicted data
        # *******************************************************

        print('writing results for {} to {}'.format(sdr.path_dict['sample_name'][reco_sample.name], os.path.join(result_paths.sample_dir_path(reco_sample.name), file_name)))
        reco_sample.dump(os.path.join(result_paths.sample_dir_path(reco_sample.name), file_name))
