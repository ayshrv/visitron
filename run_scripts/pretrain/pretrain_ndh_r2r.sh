cpu="python"
single_gpu="python"
multi_gpu_data_parallel="python"
multi_gpu_dist_data_parallel="python -m torch.distributed.launch --nproc_per_node 4 --nnodes 1 --node_rank 0"

case $1 in
    cpu)
        setting="CUDA_VISIBLE_DEVICES=-1 $cpu"
        ;;
    single-gpu)
        setting="CUDA_VISIBLE_DEVICES=$2 $single_gpu"
        ;;
    multi-gpu-dp)
        setting=$multi_gpu_data_parallel
        ;;
    multi-gpu-ddp)
        setting=$multi_gpu_dist_data_parallel
        ;;
    *)
    echo Unknown setting, Options: cpu, single-gpu \$GPU_ID, multi-gpu-dp, multi-gpu-ddp. Optionally add SLURM INFO after this.
    exit 1
    ;;
esac

file="tasks/viewpoint_select/pretrain.py"

arguments="
--img_feat_dir srv/img_features
--img_feature_file ResNet-101-faster-rcnn-genome-worientation
--data_dir srv/task_data/NDH/data
--model_name_or_path srv/oscar_weights/base-vg-labels/ep_107_1192087
--output_dir srv/results/pretrain/pretrain-masked_lm-1_in_36_viewpoint-ndh_r2r-$1
--add_ndh_data
--add_r2r_data
--max_seq_length 768
--img_feature_dim 2054
--per_gpu_train_batch_size 2
--action_space 36
--learning_rate 5e-05
--weight_decay 0.05
--num_epochs 20
--warmup_steps 0
--drop_out 0.3
--logging_steps 10
--save_steps 100
--seed 88
--num_workers 0
"
# --evaluate_during_training

command_to_run="${setting} ${file} ${arguments}"
echo $command_to_run
echo
eval $command_to_run
