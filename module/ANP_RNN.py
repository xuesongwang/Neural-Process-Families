import torch.nn as nn
import torch
import numpy as np
from module.basic_module import DeterministicDecoder, DeterministicEncoder, LatentEncoder, BatchNormSequence

class RecurrentAttentiveNeuralProcess(nn.Module):
    """(Attentive) Neural Process module.

    See https://arxiv.org/abs/1807.01613 for details.

    Args:
        input_dim (int): Dimensionality of the input.
        latent_dim (int): Dimensionality of the hidden representation.
        output_dim (int): Dimensionality of the input signal.
        use_attention (bool, optional): Switch between ANPs and CNPs. Defaults
            to `False`.
    """

    def __init__(self,
                 input_dim,
                 latent_dim,
                 output_dim,
                 use_attention= True,
                 use_rnn = True):
        super(RecurrentAttentiveNeuralProcess, self).__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.output_dim = output_dim
        self.use_attention = use_attention

        # normalization, try if still worked when removed later
        self.norm_x = BatchNormSequence(input_dim, affine=False)
        self.norm_y = BatchNormSequence(output_dim, affine=False)

        self.x_encoder = nn.LSTM(self.input_dim, self.latent_dim, batch_first=True, num_layers=2, dropout=0.7)
        self.y_encoder = nn.LSTM(self.output_dim, self.latent_dim, batch_first=True, num_layers=2, dropout=0.7)

        # change in/out dimension to be more readable
        input_dim = self.latent_dim
        output_dim = self.latent_dim

        self.deter_encoder = \
            DeterministicEncoder(input_dim= input_dim + output_dim,
                                 attent_input_dim = self.latent_dim,
                                latent_dim=self.latent_dim,
                                use_attention=use_attention)

        self.latent_encoder = \
            LatentEncoder(input_dim=input_dim + output_dim,
                            latent_dim=self.latent_dim)
        self.decoder = DeterministicDecoder(input_dim=self.latent_dim,
                                       latent_dim=self.latent_dim,
                                       output_dim=self.output_dim,
                                       include_latent=True)

    def forward(self, x_context, y_context, x_target, y_target = None):
        """Forward pass through NP.

        Args:
            x_context (tensor): Context locations of shape
                `(batch, num_context, input_dim_x)`.
            y_context (tensor): Context values of shape
                `(batch, num_context, input_dim_y)`.
            x_target (tensor): Target locations of shape
                `(batch, num_target, input_dim_x)`.

        Returns:
            (Mean, var), dist : Result of decoder, and the distribution of the latent encoder
        """

        n = x_context.shape[1]
        #normalization
        x_context = self.norm_x(x_context)
        x_target = self.norm_x(x_target)
        y_context = self.norm_y(y_context)

        x_context, _ = self.x_encoder(x_context)
        x_target, _ = self.x_encoder(x_target)
        y_context, _ = self.y_encoder(y_context)
        r = self.deter_encoder(x_context, y_context, x_target)
        z_dist = self.latent_encoder(x_context, y_context)
        if y_target is None:
            z = z_dist.rsample()
            z_dist_post = None
        else:
            y_target = self.norm_y(y_target)
            y_target, _ = self.y_encoder(y_target)
            z_dist_post = self.latent_encoder(x_target, y_target)
            z = z_dist_post.rsample()

        # prepare embedding concatenated with x_target
        num_target = x_target.shape[1]
        if r.shape[1] == 1:
            r = r.repeat(1, num_target, 1)
        if z.shape[1] == 1:
            z = z.repeat(1, num_target, 1)
        representation = torch.cat([r, z], dim=-1)
        return self.decoder(x_target, representation, n), z_dist, z_dist_post

    @property
    def num_params(self):
        """Number of parameters."""
        return np.sum([torch.tensor(param.shape).prod()
                       for param in self.parameters()])

