from .utils import denormalize_residual, denormalize_data, normalize_data

import torch
import numpy as np


def infer(model, mel_prediction, duration_prediction, config):
    device = config['main']['device']
    synthesized_spec = mel_prediction.transpose(0,2,1)
    synthesized_spec = torch.from_numpy(synthesized_spec).to(device)
    if config['data']['normallize_spectrum']:
        synthesized_spec = normalize_data(synthesized_spec)
    
    if config['model']['model_type2'] == "segment-based":
        durations = np.round(np.exp(duration_prediction.squeeze()) - 1)

        all_mask, all_segment_spec, all_start_points, all_spec_size = [], [], [], []
        pred = torch.zeros(synthesized_spec.shape)
        
        ## Create segments of date exept last segment 
        start_phoneme_index = 0
        end_phoneme_index = 0
        for i in range(1, len(durations)+1):
            win_length = int(sum(durations[start_phoneme_index:i]))
            if win_length > config['data']['max_win_length']:
                end_phoneme_index = i-1
                start_point = int(sum(durations[:start_phoneme_index]))
                end_point = int(sum(durations[:end_phoneme_index]))
                segment_spec = synthesized_spec[:,:,start_point:end_point]
                all_start_points.append(start_point)
                spec_size = segment_spec.shape[-1]
                all_spec_size.append(spec_size)
                segment_spec = torch.nn.functional.pad(segment_spec, (0, config['data']['max_win_length']-spec_size), mode = "constant", value = 0.0)
                mask = torch.ones((1, segment_spec.shape[-1])).to(device)
                mask[:,spec_size:] = 0
                all_mask.append(mask.unsqueeze(0))
                all_segment_spec.append(segment_spec)  
                start_phoneme_index = end_phoneme_index
        
        ## Create last segment of data with overlapping to last previous segments
        start_phoneme_index = len(durations)
        end_phoneme_index = len(durations)
        for i in range(len(durations)):
            start_phoneme_index -= 1
            win_length = int(sum(durations[start_phoneme_index:]))
            if win_length > config['resgrad']['max_win_length']:
                start_phoneme_index += 1
                start_point = int(sum(durations[:start_phoneme_index]))
                end_point = int(sum(durations[:end_phoneme_index]))
                segment_spec = synthesized_spec[:,:,start_point:end_point]
                all_start_points.append(start_point)
                spec_size = segment_spec.shape[-1]
                all_spec_size.append(spec_size)
                segment_spec = torch.nn.functional.pad(segment_spec, (0, config['data']['max_win_length']-spec_size), mode = "constant", value = 0.0)
                mask = torch.ones((1, segment_spec.shape[-1])).to(device)
                mask[:,spec_size:] = 0
                all_mask.append(mask.unsqueeze(0))
                all_segment_spec.append(segment_spec)  
                break

        mask = torch.cat(all_mask).to(device)
        segment_spec = torch.cat(all_segment_spec).to(device)
        z = segment_spec + torch.randn_like(segment_spec, device=device) / 1.5
        segments_pred = model(z, mask, segment_spec, n_timesteps=25, stoc=False, spk=None)

        for i in range(len(segments_pred)):
            segment_pred = segments_pred[i,:,:all_spec_size[i]]
            pred[:,:,all_start_points[i]:all_start_points[i]+all_spec_size[i]] = segment_pred
    else:
        mask = torch.ones(synthesized_spec.shape).to(device)
        z = synthesized_spec + torch.randn_like(synthesized_spec, device=device) / 1.5
        pred = model(z, mask, synthesized_spec, n_timesteps=50, stoc=False, spk=None)
    pred = pred.to(device)
    
    if config['model']['model_type1'] == "spec2residual":
        if config['data']['normallize_residual']:
            spec_pred =  denormalize_residual(pred) + synthesized_spec
        else:
            spec_pred =  pred + synthesized_spec
    else:
        spec_pred = pred

    if config['data']['normallize_spectrum']:
        spec_pred = denormalize_data(spec_pred)

    return spec_pred