import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import weblogolib as wl
from seqLogo import utils


_sizes = {
    'small': 3.54,
    'medium': 5,
    'large': 7.25,
    'xlarge': 10.25
}


def seqLogo(pwm, ic_scale = True, color_scheme = None, size = 'medium',
            format = 'svg', output_name = None, **kwargs):
    """The plotting method of the `seqLogo` distribution.

    Given an `M x N` PWM matrix, where `M` is the number of positions and `N`
    is the number of letters, calculate and render a WebLogo-like motif plot.

    When `ic_scale` is `True`, the height of each column is proportional to 
    its information content. The y-axis label and scale will reflect information
    content. Otherwise, all columns have the same height and y-axis label will
    reflect "bits"

    Args:
        pwm (`seqLogo.Pwm`): a pre-formatted PWM instance
        ic_scale (bool): whether or not to scale the column heights (default: True)
        size (str): small (3.54 in), medium (5 in), large (7.25 in), xlarge (10.25) (default: 'medium')
        format (str): desired matplotlib supported output format Options are 'eps', 'pdf', 'png', 'jpeg', and 'svg' (default: "svg")
        output_name (None | str): Name of the file to save the figure. If `None`:
            the figure will not be saved. (default: None)
        color_scheme (str): the color scheme to use for weblogo:
            'auto': None
            'monochrome': all black
            'base pairing': (NA Only) TAU are orange, GC are blue
            'classic': (NA Only) classic WebLogo color scheme for nucleic acids
            'hydrophobicity': (AA only) Color based on hydrophobicity
            'chemistry': (AA only) Color based on chemical properties
            'charge': (AA Only) Color based on charge
        **kwargs: all additional keyword arguments found at http://weblogo.threeplusone.com/manual.html 
    """
    # Ensure color scheme matches the alphabet
    if pwm.alphabet_type in utils.NA_ALPHABETS:
        if color_scheme is None:
            color_scheme = 'classic'
        if color_scheme not in utils.NA_COLORSCHEMES:
            raise ValueError(f'{color_scheme} color_scheme selected is not an allowed nucleic acid color scheme')
    if pwm.alphabet_type in utils.AA_ALPHABETS:
        if color_scheme is None:
            color_scheme = 'hydrophobicity'
        if color_scheme not in utils.AA_COLORSCHEMES:
            raise ValueError(f'{color_scheme} color_scheme selected is not an allowed amino acid color scheme')

    color_scheme = wl.std_color_schemes[color_scheme]

    # Setup the format writer
    out_format = wl.formatters[format]

    # Prepare the logo size
    stack_width = (_sizes[size]/pwm.length) * 72

    # Initialize the options
    if ic_scale:
        unit_name = 'bits'
    else:
        unit_name = 'probability'
    options = wl.LogoOptions(unit_name = unit_name, color_scheme = color_scheme,
                            show_fineprint = False, stack_width = stack_width, **kwargs)

    #Initialize the output format
    logo_format = wl.LogoFormat(pwm, options)

    out = out_format(pwm, logo_format)

    # Create the file if the user supplied an output_name
    if output_name:
        out_file = open(f'{output_name}.{format}', 'wb')
        out_file.write(out)
        out_file.close()

    try:
        if get_ipython():
            import IPython.display as ipd
            if format == 'svg':
                ipd.display(ipd.SVG(out))
            elif format in ('png', 'jpeg', 'svg'):
                ipd.display(ipd.Image(out))
            else:
                raise ValueError(f'{format} format not supported for plotting in console')
            if output_name:
                with open(output_name, 'wb') as out_file:
                    out_file.write(out)
    except NameError:
        if output_name is None:
            raise ValueError('If not in an IPython/Jupyter console and no output_name is given, nothing will be rendered')
        else:
            with  open(f'{output_name}.{format}', 'wb') as out_file:
                out_file.write(out)
