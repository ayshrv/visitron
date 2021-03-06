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

file="tasks/viewpoint_select/train_classifier.py"

arguments="
--img_feat_dir srv/img_features
--img_feature_file ResNet-152-imagenet.tsv
--data_dir srv/task_data/NDH/data
--model_name_or_path srv/results/viewpoint_select/ndh_rxr-pretrain_ndh_r2r/checkpoints/checkpoint-3710
--output_dir srv/results/classifier/teacher_force-frozen-2layers_weight5-$1
--only_finetune_classifier
--question_asking_class_weight 5
--max_seq_length 768
--img_feature_dim 2054
--lstm_img_feature_dim 2048
--per_gpu_train_batch_size 1
--per_gpu_eval_batch_size 1
--learning_rate 5e-05
--weight_decay 0.05
--num_iterations 50000
--warmup_steps 0
--drop_out 0.3
--logging_steps 10
--eval_logging_steps 500
--save_steps 100
--seed 88
--num_workers 0
"
# --evaluate_during_training

command_to_run="${setting} ${file} ${arguments}"
echo $command_to_run
echo
eval $command_to_run
