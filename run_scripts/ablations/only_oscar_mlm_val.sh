cpu="python"
single_gpu="python"
multi_gpu_data_parallel="python"
multi_gpu_dist_data_parallel="python -m torch.distributed.launch --nproc_per_node 4 --nnodes 1 --node_rank 0"

case $1 in
    cpu)
        setting="CUDA_VISIBLE_DEVICES=-1 $cpu"
        slurm_info=$2
        ;;
    single-gpu)
        setting="CUDA_VISIBLE_DEVICES=$2 $single_gpu"
        slurm_info=$3
        ;;
    multi-gpu-dp)
        setting=$multi_gpu_data_parallel
        slurm_info=$2
        ;;
    multi-gpu-ddp)
        setting=$multi_gpu_dist_data_parallel
        slurm_info=$2
        ;;
    *)
    echo Unknown setting, Options: cpu, single-gpu \$GPU_ID, multi-gpu-dp, multi-gpu-ddp. Optionally add SLURM INFO after this.
    exit 1
    ;;
esac

file="tasks/viewpoint_select/train.py"

eval_iters=""
for (( COUNTER=10; COUNTER<=50000; COUNTER+=100 )); do
    eval_iters="$eval_iters $COUNTER"
done

# eval_iters="16310"

exp_name=srv/results/viewpoint_select/ndh-only_oscar_mlm

arguments="
--img_feat_dir srv/img_features
--img_feature_file ResNet-152-imagenet.tsv
--data_dir srv/task_data/NDH/data
--model_name_or_path $exp_name/checkpoints/
--output_dir $exp_name-val
--path_type planner_path
--max_seq_length 768
--img_feature_dim 2054
--lstm_img_feature_dim 2048
--eval_only
--eval_iter $eval_iters
--per_gpu_eval_batch_size 8
--drop_out 0.3
--seed 88
--num_workers 0
--slurm_info '$slurm_info'
"

command_to_run="${setting} ${file} ${arguments}"
echo $command_to_run
echo
eval $command_to_run
