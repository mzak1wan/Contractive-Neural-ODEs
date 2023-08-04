# from phase2_light_lognorms_global import ImageClassifier_CIFAR_global
from phase2_light_global import ImageClassifier_CIFAR_global
from torchvision import datasets, transforms
import torch
from torchattacks import FGSM, PGD
from torch import nn
import pytorch_lightning as pl
import numpy as np
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from robustbench import load_model
from model import *
from utils import *
from utils_plus import (upper_limit, lower_limit, std, clamp, get_loaders,
    attack_pgd, evaluate_pgd, evaluate_standard, normalize)
from torch.utils.data import Subset
from autoattack import AutoAttack
# from torchattacks import AutoAttack
folder_savemodel = './neurips2023/MNIST/models' # feature extractor


device = "cuda"
fc_dim = 64

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', default=128, type=int)
    parser.add_argument('--data-dir', default='.data/cifar', type=str)
    parser.add_argument('--epsilon', default=8, type=int)
    parser.add_argument('--out-dir', default='train_fgsm_output', type=str, help='Output directory')
    parser.add_argument('--seed', default=0, type=int, help='Random seed')
    return parser.parse_args()

args = get_args()


def accuracy(model, dataset_loader):
    total_correct = 0
    for x, y in dataset_loader:
        x = x.to(device)
        y = one_hot(np.array(y.numpy()), 10)
        target_class = np.argmax(y, axis=1)
        predicted_class = np.argmax(model(x).cpu().detach().numpy(), axis=1)
        total_correct += np.sum(predicted_class == target_class)
    return total_correct / len(dataset_loader.dataset)


#loading the robust feature extractor
robust_backbone = load_model(model_name='Rebuffi2021Fixing_70_16_cutmix_extra', dataset='cifar10', threat_model='Linf')
robust_backbone.logits = Identity()
robust_backbone_fc_features = MLP_OUT_ORTH1024()
fc_layers_phase1 = MLP_OUT_BALL()
net_save_robustfeature = nn.Sequential(robust_backbone, robust_backbone_fc_features, fc_layers_phase1).to(device)


robust_feature_savefolder = './neurips2023/CIFAR10/EXP/CIFAR10_resnet'
saved_temp = torch.load(robust_feature_savefolder+'/ckpt.pth')
statedic_temp = saved_temp['net_save_robustfeature']
net_save_robustfeature.load_state_dict(statedic_temp)
    

#loading the cnode + mlp 
# str_reg_suf = './neurips2023/CIFAR10/EXP_Global/test_lightning_model.ckpt'  # global nodes
# str_reg_suf = './neurips2023/CIFAR10/EXP_Global/orthogonal_lightning_model.ckpt'
# str_reg_suf = './neurips2023/CIFAR10/EXP_Global/orthogonal_lognorms_cnode_lightning_model.ckpt'
# str_reg_suf = './neurips2023/CIFAR10/EXP_Global/orthogonal_final2_lightning_model.ckpt'
str_reg_suf = './neurips2023/CIFAR10/EXP_Global/fixed_node_lightning_model.ckpt'
ODE_FCmodel = ImageClassifier_CIFAR_global.load_from_checkpoint(str_reg_suf)


# Full model
new_model_full = nn.Sequential(robust_backbone, robust_backbone_fc_features, ODE_FCmodel).to(device)
new_model_full.eval()

trainloader, testloader, train_eval_loader, test_dataset = get_loaders(args.data_dir, args.batch_size)

test_loader = testloader

l = [x for (x, y) in test_loader]
x_test = torch.cat(l, 0)
l = [y for (x, y) in test_loader]
y_test = torch.cat(l, 0)


##### here we split the set to multi servers and gpus to speed up the test. otherwise it is too slow.
##### if your server is powerful or your have enough time, just use the full dataset directly by commenting out the following.
#############################################    
# iii = 4
# size_auto = 500
# x_test = x_test[size_auto*iii:size_auto*(iii+1),...]
# y_test = y_test[size_auto*iii:size_auto*(iii+1),...]

#############################################   

print('run_standard_evaluation_individual', 'Linf')
print(x_test.shape)
device = torch.device('cuda',index=2) 
epsilon = 8 / 255.
# adversary = AutoAttack(new_model_full.to(device), norm='Linf', eps=epsilon, version='standard',verbose=True, device= device)
adversary = AutoAttack(new_model_full.to(device), norm='Linf', eps=epsilon, version='standard',verbose=True, device= device)
# # adversary = AutoAttack(new_model_full, norm='Linf', eps=epsilon, version='standard',verbose=True)
# # adversary = AutoAttack(new_model_full, norm='Linf', eps=8/255, version='standard', n_classes=10, seed=None, verbose=True)

# # adv_images = adversary(x_test, y_test)
with torch.no_grad():
    X_adv = adversary.run_standard_evaluation(x_test, y_test, bs=128)