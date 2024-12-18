# Import các thư viện cần thiết để build model
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import GPT2LMHeadModel # Thư viện chứa mô hình GPT-2
from types import SimpleNamespace
from timm import create_model # Sử dụng thư viện timm để tạo mô hình Vision Transformer (ViT)

# Class GPT2Attention thực hiện cơ chế Self-Attention của GPT-2
class GPT2Attention(nn.Module):
    def __init__(self,config):
        super().__init__()
        # Định nghĩa kích thước embedding và số lượng head trong Attention
        self.embed_dim = config.embed_dim
        self.n_heads = config.num_heads
        assert self.embed_dim % self.n_heads == 0 # Kích thước embedding phải chia hết cho số head
        self.head_size = self.embed_dim // self.n_heads
        self.seq_len = config.seq_len
        
        # Các lớp Linear để tính toán Query, Key, Value và lớp chuẩn hóa Attention
        self.c_attn = nn.Linear(self.embed_dim, self.head_size * self.n_heads * 3,bias=True)
        self.scale = self.head_size ** -0.5
        
        # Triangular Mask để che các giá trị không hợp lệ
        self.register_buffer('mask',torch.tril(torch.ones(1,1,self.seq_len,self.seq_len)))
        
        # Lớp Linear để đưa đầu ra về đúng kích thước
        self.c_proj = nn.Linear(self.embed_dim, self.embed_dim, bias=True)
        
        # Dropout để tránh overfitting
        self.attn_dropout = nn.Dropout(config.attention_dropout)
        self.resid_dropout = nn.Dropout(config.residual_dropout)       
        
    def forward(self, x):
        b,t,c = x.shape
        # Tách embedding thành Query (q), Key (k), và Value (v)
        q,k,v = self.c_attn(x).chunk(3,dim=-1)
        q = q.view(b,t,self.n_heads,self.head_size).permute(0,2,1,3) # (batch, head, seq_len, head_dim)
        k = k.view(b,t,self.n_heads,self.head_size).permute(0,2,1,3)
        v = v.view(b,t,self.n_heads,self.head_size).permute(0,2,1,3)
        
        # Tính toán ma trận Attention
        qk_t = (q@k.transpose(-2,-1)) * self.scale
        qk_t = qk_t.masked_fill(self.mask[:,:,:t,:t]==0,float('-inf'))
        qk_t = F.softmax(qk_t,dim=-1) # Áp dụng Softmax để chuẩn hóa
        weights = self.attn_dropout(qk_t)
        
        # Tính đầu ra Attention
        attention = weights @ v 
        attention = attention.permute(0,2,1,3).contiguous().view(b,t,c) 
        
        # Kết hợp lại và áp dụng dropout
        out = self.c_proj(attention)
        out = self.resid_dropout(out)
        return out
    
# Lớp GPT2CrossAttention thực hiện cơ chế Cross-Attention
class GPT2CrossAttention(nn.Module):
    def __init__(self,config):
        super().__init__()
        # Các lớp Linear để tính toán Query, Key và Value
        self.embed_dim = config.embed_dim
        self.n_heads = config.num_heads
        assert self.embed_dim % self.n_heads == 0 # Kích thước embedding phải chia hết cho số head
        self.head_size = self.embed_dim // self.n_heads
        self.seq_len = config.seq_len
        
        self.q = nn.Linear(self.embed_dim,self.embed_dim)
        self.k = nn.Linear(self.embed_dim,self.embed_dim)
        self.v = nn.Linear(self.embed_dim,self.embed_dim)
        self.scale = self.head_size ** -0.5
        
        # Các lớp chuẩn hóa và dropout
        self.c_proj = nn.Linear(self.embed_dim, self.embed_dim, bias=True)
        self.attn_dropout = nn.Dropout(config.attention_dropout)
        self.resid_dropout = nn.Dropout(config.residual_dropout)
        
        self.apply(self._init_weights)
        
    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        
        
    def forward(self, q,k,v):
        b,t,c = q.shape
        
        q = self.q(q)
        k = self.k(k)
        v = self.v(v)
        
        # Chia và sắp xếp lại kích thước của Query, Key, Value
        q = q.view(b,q.size(1),self.n_heads,self.head_size).permute(0,2,1,3) 
        k = k.view(b,k.size(1),self.n_heads,self.head_size).permute(0,2,1,3)
        v = v.view(b,v.size(1),self.n_heads,self.head_size).permute(0,2,1,3)
        
        # Tính toán Attention
        qk_t = (q@k.transpose(-2,-1)) * self.scale
        qk_t = F.softmax(qk_t,dim=-1)
        weights = self.attn_dropout(qk_t)
        
        # Tính đầu ra Attention
        attention = weights @ v 
        attention = attention.permute(0,2,1,3).contiguous().view(b,t,c)
        
        # Kết hợp và áp dụng dropout
        out = self.c_proj(attention)
        out = self.resid_dropout(out)
        
        return out
    
# Lớp GPT2MLP xử lý tầng MLP của mô hình
class GPT2MLP(nn.Module):
    def __init__(self,config):
        super().__init__()
        # Kích thước embedding và tỉ lệ MLP
        self.embed_dim = config.embed_dim
        self.mlp_ratio = config.mlp_ratio
        self.mlp_dropout = config.mlp_dropout
        
        # Hai lớp Linear và hàm kích hoạt GELU
        self.c_fc = nn.Linear(self.embed_dim,self.embed_dim*self.mlp_ratio)
        self.c_proj = nn.Linear(self.embed_dim*self.mlp_ratio,self.embed_dim)
        self.act = nn.GELU() # Hàm kích hoạt
        self.dropout = nn.Dropout(self.mlp_dropout) # Dropout để giảm overfitting
        
    def forward(self,x):
        x = self.c_fc(x) 
        x = self.act(x) 
        x = self.c_proj(x) 
        x = self.dropout(x) 
        return x
    
# Class GPT2Block chứa các thành phần chính của GPT-2
class GPT2Block(nn.Module):
    def __init__(self,config):
        super().__init__()
        # Kích thước embedding và các thành phần của Block
        self.embed_dim = config.embed_dim
        self.ln_1 = nn.LayerNorm(self.embed_dim) 
        self.attn = GPT2Attention(config) 
        self.ln_2 = nn.LayerNorm(self.embed_dim) 
        self.mlp = GPT2MLP(config) 
        self.ln_3 = nn.LayerNorm(self.embed_dim) 
        self.cross_attn = GPT2CrossAttention(config) 
        
    def forward(self,x,enc_out):
        x = x+self.attn(self.ln_1(x)) # Self-Attention
        x = x+self.cross_attn(self.ln_2(x),enc_out,enc_out) # Cross-Attention
        x = x+self.mlp(self.ln_3(x)) # MLP
        return x
    
# Class VisionGPT2Model kết hợp Vision Transformer và GPT-2
class VisionGPT2Model(nn.Module):
    def __init__(self,config):
        super().__init__()
        
        self.config = config
        
        # ViT trích xuất đặc trưng hình ảnh
        vit = create_model('vit_base_patch16_224',pretrained=False,num_classes=0)
        self.patch_embed = vit.patch_embed
        num_patches = self.patch_embed.num_patches
        
        self.cls_token = vit.cls_token # Token class
        embed_len = num_patches + vit.num_prefix_tokens
        self.pos_embed = vit.pos_embed
        self.pos_drop = nn.Dropout(p=0.) 
        
        self.blocks = nn.ModuleList([vit.blocks[i] for i in range(config.depth)]) 
        
        # Transformer GPT-2
        self.transformer = nn.ModuleDict(dict(
            wte = nn.Embedding(config.vocab_size,config.embed_dim), 
            wpe = nn.Embedding(config.seq_len,config.embed_dim), 
            drop = nn.Dropout(config.emb_dropout), 
            h = nn.ModuleList([GPT2Block(config) for _ in range(config.depth)]), 
            ln_f = nn.LayerNorm(config.embed_dim)
        ))
        self.lm_head = nn.Linear(config.embed_dim,config.vocab_size,bias=False)
        self.transformer.wte.weight = self.lm_head.weight
        
    def _pos_embed(self,x):
        pos_embed = self.pos_embed
        x = torch.cat((self.cls_token.expand(x.shape[0], -1, -1), x), dim=1)
        x = x + pos_embed
        return self.pos_drop(x)
    
    def pretrained_layers_trainable(self,trainable=False):
        layers = [
            self.cls_token, self.patch_embed, self.pos_embed, self.blocks,
            self.transformer.wte, self.transformer.wpe,
            self.transformer.ln_f, self.lm_head
        ]
        gpt_layers = [[
            self.transformer.h[i].ln_1,self.transformer.h[i].ln_2,
            self.transformer.h[i].attn,self.transformer.h[i].mlp
        ] for i in range(self.config.depth)]
        for l in gpt_layers:
            layers.extend(l)
        
        for layer in layers:
            if not isinstance(layer,nn.Parameter):
                for p in layer.parameters():
                    p.requires_grad = trainable
            else:
                layer.requires_grad = trainable
                
        total_frozen_params = sum([p.numel() for p in self.parameters() if not p.requires_grad])
        print(f'{total_frozen_params=}')
        
    def unfreeze_gpt_layers(self,):
        # Unfreeze các layer GPT-2
        gpt_layers = [[
            self.transformer.h[i].ln_1,self.transformer.h[i].ln_2,
            self.transformer.h[i].attn,self.transformer.h[i].mlp
        ] for i in range(self.config.depth)]
        flatten = []
        for l in gpt_layers:
            flatten.extend(l)
            
        for layer in flatten:
            if not isinstance(layer,nn.Parameter):
                for p in layer.parameters():
                    p.requires_grad = True
            else:
                layer.requires_grad = True
        
    @classmethod    
    def from_pretrained(self,config):
        model = VisionGPT2Model(config)
        sd = model.state_dict()
        keys = sd.keys()
        ignore_matches = ['blocks.','cross_attn.','ln_3','cls_token','pos_embed','patch_embed.','.attn.mask']
        vit_keys = [key for key in keys if any(match in key for match in ignore_matches)]
        gpt_keys = [key for key in keys if key not in vit_keys]
        
        gpt2_small = GPT2LMHeadModel.from_pretrained('gpt2')
        sd_hf = gpt2_small.state_dict()
        hf_keys = sd_hf.keys()
        hf_keys = [k for k in hf_keys if not k.endswith('.attn.masked_bias')]
        hf_keys = [k for k in hf_keys if not k.endswith('.attn.bias')]
        transposed = ['attn.c_attn.weight', 'attn.c_proj.weight', 'mlp.c_fc.weight', 'mlp.c_proj.weight']
        
        for k in hf_keys:
            if any(match in k for match in ignore_matches):
                continue
            if any(k.endswith(w) for w in transposed):
                assert sd_hf[k].shape[::-1] == sd[k].shape
                with torch.no_grad():
                    sd[k].copy_(sd_hf[k].t())
            else:
                assert sd_hf[k].shape == sd[k].shape
                with torch.no_grad():
                    sd[k].copy_(sd_hf[k])
            
        model.load_state_dict(sd)
        
        return model
    
    def forward(self,image,input_ids,labels=None):
        
        image = self.patch_embed(image)
        image = self._pos_embed(image)
        
        token_embeddings = self.transformer.wte(input_ids) 
        pos_embs = torch.arange(0,input_ids.size(1)).to(input_ids.device)
        positional_embeddings = self.transformer.wpe(pos_embs)
        input_ids = self.transformer.drop(token_embeddings+positional_embeddings)
        
        for i in range(self.config.depth):
            image = self.blocks[i](image)
            input_ids = self.transformer.h[i](input_ids, image)
        
        input_ids = self.transformer.ln_f(input_ids)
        
        if labels is not None:
            lm_logits = self.lm_head(input_ids)
            loss = F.cross_entropy(lm_logits.view(-1, lm_logits.shape[-1]), labels.view(-1))
            return loss
        
        lm_logits = self.lm_head(input_ids[:,[-1],:])
        return lm_logits
    
    def generate(self,image,sequence,max_tokens=50,temperature=1.0,deterministic=False,eos_token_id=50256):
        for _ in range(max_tokens):
            out = self(image,sequence)
            out = out[:,-1,:] / temperature
            probs = F.softmax(out,dim=-1)
            if deterministic:
                next_token = torch.argmax(probs,dim=-1,keepdim=True)
            else:
                next_token = torch.multinomial(probs,num_samples=1)
            sequence = torch.cat([sequence,next_token],dim=1)
            if next_token.item() == eos_token_id:
                break
            
        return sequence.cpu().flatten()
    

if __name__ == '__main__':
    model_config = SimpleNamespace(
        vocab_size = 50_257,
        embed_dim = 768,
        num_heads = 12,
        seq_len = 1024,
        depth = 12,
        attention_dropout = 0.1,
        residual_dropout = 0.1,
        mlp_ratio = 4,
        mlp_dropout = 0.1,
        emb_dropout = 0.1,
    )
    
    # Model này đã được train để tạo caption từ hình ảnh
    model = VisionGPT2Model.from_pretrained(model_config)
