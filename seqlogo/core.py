import numpy as np
import pandas as pd
from seqlogo import utils
from functools import singledispatch, partial
from numbers import Real
from collections.abc import Collection


# Check to see if currently within an IPython console
try:
    if get_ipython():
        from IPython.display import display
        ipy = True
except NameError:
    ipy = False
    

def _init_pm(pm_matrix, pm_type = 'ppm', alphabet_type = 'DNA', alphabet = None):
    """Checks for the file (if filename is supplied) and reads it in if present.
    Otherwise it just ensures that the position matrix (PM) dimensions match the
    expected alphabet.

    Args:
        pm_matrix (str or `numpy.ndarray` or `pandas.DataFrame`): The user supplied
                        PM. If it is a filename, the file will be opened
                        and parsed. If it is an `numpy.ndarray` or `pandas.DataFrame`,
                        it will just be assigned. (default: None))
        pm_type (str): whether the PM is a PWM or PFM (default: 'pwm')
        alphabet_type (str): Desired alphabet to use. Order matters (default: 'DNA')
                "DNA" := "ACGT"
                "reduced DNA" := "ACGTN-"
                "ambig DNA" := "ACGTRYSWKMBDHVN-"
                "RNA" := "ACGU"
                "reduced RNA" := "ACGUN-"
                "ambig RNA" := "ACGURYSWKMBDHVN-"
                "AA" : = "ACDEFGHIKLMNPQRSTVWY"
                "reduced AA" := "ACDEFGHIKLMNPQRSTVWYX*-"
                "ambig AA" := "ACDEFGHIKLMNOPQRSTUVWYBJZX*-"
                (default: "DNA")
        alphabet (str): if 'custom' is selected or a specialize alphabet is desired, this accepts a string (default: None)

    Returns:
        pm (pd.DataFrame): a properly formatted PM instance object

    Raises:
        FileNotFoundError if `pm_filename_or_array` is a string, but not a file
        ValueError if desired alphabet is not supported
        ValueError if the PM is not well formed
        ValueError if the probabilities do not add up to 1
        TypeError if `pm_filename_or_array` is not a file or array-like structure
    """
    pm = _submit_pm(pm_matrix)

    if alphabet_type != 'custom':
        ex_alph_len = len(utils._IDX_LETTERS[alphabet_type])
    else:
        ex_alph_len = len(alphabet)

    if not pm.shape[1] == ex_alph_len:
        if alphabet_type in utils._NA_ALPHABETS or alphabet_type in utils._AA_ALPHABETS or alphabet_type == 'custom':
            if pm.shape[0] == ex_alph_len:
                pm = pm.transpose()
            else:
                raise ValueError('{} alphabet selected, but PM is not {} rows long'.format(alphabet, ex_alph_len))

    if alphabet_type != 'custom':
        pm.columns = list(utils._IDX_LETTERS[alphabet_type])
    else:
        pm.columns = list(alphabet)

    if pm_type == 'ppm':
        if not np.allclose(pm.sum(axis=1), 1, 1e-10):
            raise ValueError('All or some PPM columns do not add to 1')

    return pm


@partial(np.vectorize, otypes = [np.float64])
def __proportion(prob):
    """Vectorized proportion formula that feeds into _row_wise_ic

    Args:
        prob (`np.float64`): probability for a given letter at given position

    returns (`np.float64`): normalized probability
    """
    if prob > 0:
        return prob * np.log2(prob)
    else:
        return 0


def _row_wise_ic(row):
    """Get the information content for each row across all letters

    Args:
        row (`pandas.Series`): row from the PWM

    Returns:
        The information content for the row
    """
    return 2 + np.sum(__proportion(row), axis = 1)


class Pm:
    """Main class for handling Position Matrices (PM).

    Base class for creating PMs. Will calculate both consensus sequence and information
    content if the pm_type is set to either 'ppm' or 'pwm'

    Attributes:
        pm (`pandas.DataFrame`): PM DataFrame generated by user-submitted PM
        consensus (str): The consensus sequence determined by the PM
        ic (`numpy.ndarray`): The information content for each position
        width (int): Length of the sequence/motif
        length (int): an alias for `width`
        alphabet_type (str): Desired alphabet type to use. (default: 'DNA')
        alphabet (str): Desired alphabet to use. Order matters (default: None)
        weight (`numpy.array`): 1-D array of ones. Used for WebLogo compatability. If the chosen
                alphabet type allows gaps, will base weights on gap average in that position
        counts (`pandas.DataFrame`): Counts of letters at the given position. If
                `counts` is not supplied (because PPM was the entry-point), the PPM will be cast
                as a PFM by multiplying it by 100
        pseudocount: some number to offset PPM values at to prevent -inf/+inf (default: 1e-10)
        background (Collection): must be an iterable with length of alphabet with each letter's respective respective background probability or constant. (default: for NA-0.25, for AA-Robinson-Robinson Frequencies)
    """
    
    __all__ = ['pm', 'consensus', 'ic', 'width', 'counts', 'entropy'
               'alphabet', 'alphabet_type', 'length', 'weight']
    
    def __init__(self, pm_filename_or_array = None, pm_type = 'ppm', alphabet_type = 'DNA', alphabet = None, 
                 background = None, pseudocount = None):
        """Initializes the Pm

        Creates the Pm instance. If the user does not define `pm_filename_or_array`,
        it will be initialized to empty. Will generate all other attributes as soon
        as a `pm_filename_or_array` is supplied.

        Args:
            pm_filename_or_array (str or `numpy.ndarray` or `pandas.DataFrame` or Pm): The user supplied
                PM. If it is a filename, the file will be opened
                and parsed. If it is an `numpy.ndarray` or `pandas.DataFrame`,
                it will just be assigned. (default: None, skips '#' comment lines)
            alphabet_type (str): Desired alphabet to use. Order matters (default: 'DNA')
                "DNA" := "ACGT"
                "reduced DNA" := "ACGTN-"
                "ambig DNA" := "ACGTRYSWKMBDHVN-"
                "RNA" := "ACGU"
                "reduced RNA" := "ACGUN-"
                "ambig RNA" := "ACGURYSWKMBDHVN-"
                "AA" : = "ACDEFGHIKLMNPQRSTVWY"
                "reduced AA" := "ACDEFGHIKLMNPQRSTVWYX*-"
                "ambig AA" := "ACDEFGHIKLMNOPQRSTUVWYBJZX*-"
                "custom" := None
                (default: 'DNA')
            alphabet (str): if 'custom' is selected or a specialize alphabet is desired, this accepts a string (default: None)
            background (constant or Collection): Offsets used to calculate background letter probabilities (defaults: If 
                using an Nucleic Acid alphabet: 0.25; if using an Aminio Acid alphabet: Robinson-Robinson Frequencies)
            pseudocount (constant): Some constant to offset PPM conversion to PWM to prevent -/+ inf. (default: 1e-10)
        """
        
        self._pm = self._pfm = self._ppm = self._pwm = None
        self._weight = self._width = self._consensus = None
        self._counts = self._weight = self._ic = None
        self._alphabet_type = alphabet_type
        self._alphabet = alphabet
        self._pm_type = "cpm"
        if pseudocount is None:
            self.pseudocount = 1e-10
        else:
            self.pseudocount = pseudocount
        if background is None:
            self.background = None
        else:
            self.background = background
        
        if pm_filename_or_array is not None:
            self._update_pm(pm_filename_or_array, pm_type, alphabet_type, alphabet, self.background, self.pseudocount)
        
    def _update_pm(self, pm, pm_type ='ppm', alphabet_type = 'DNA', alphabet = None, background = None, pseudocount = None):
        if alphabet_type is None:
            alphabet_type = self.alphabet_type
        setattr(self, "_{}".format(self._pm_type), _init_pm(pm, pm_type, alphabet_type, alphabet))
        self._width = self._get_width(self._get_pm)
        if not isinstance(self.pseudocount, Real):
            if len(self.pseudocount) != self.width:
                raise ValueError('pseudocount must be the same length as sequence or a constant')
        if self._alphabet_type not in ("DNA", "RNA", "AA"):
            self._weight = self._get_pm[:,:-1].sum(axis=1)/self._get_pm.sum(axis=1)
        else:
            self._weight = np.ones((self.width,), dtype=np.int8)
        self._consensus = self._generate_consensus(self._get_pm)
        self.background = _check_background(self)
        if pm_type not in ('pm', 'pfm'):
            if pm_type == 'ppm':
                self._ic = (self.ppm * ppm2pwm(self.ppm, background = self.background, pseudocount = self.pseudocount)).sum(axis = 1)
            elif pm_type == 'pwm':
                self._ic = (pwm2ppm(self.pwm, background = self.background, pseudocount = self.pseudocount) * self.pwm).sum(axis = 1)
        
    @property
    def pseudocount(self):
        return self._pseudocount
    
    @pseudocount.setter
    def pseudocount(self, pseudocount):
        self._pseudocount = pseudocount
    
    @property
    def _get_pm(self):
        return getattr(self, "_{}".format(self._pm_type))
    
    def __len__(self):
        return self._get_pm.shape[0]

    def __str__(self):
        if ipy:
            display(self._get_pm)
            return ''
        else:
            return self._get_pm.__str__()

    def __repr__(self):
        if ipy:
            display(self._get_pm)
            return ''
        else:
            return self._get_pm.__repr__()
    
    def sum(self, axis = None):
        return np.sum(self._get_pm, axis = axis)
    
    def __add__(self, other):
        return self._get_pm + other
    
    def __radd__(self, other):
        return other + self._get_pm
    
    def __sub__(self, other):
        return self._get_pm - other
    
    def _rsub_(self, other):
        return other - self._get_pm
    
    def __mul__(self, other):
        return self._get_pm * other
    
    def __rmul__(self, other):
        return other * self._get_pm
    
    def __truediv__(self, other):
        return self._get_pm / other
    
    def __rtruediv__(self, other):
        return other / self._get_pm
    
    def __floordiv__(self, other):
        return self._get_pm // other
    
    def __rfloordiv__(self, other):
        return other // self._get_pm
    
    def __divmod__(self, other):
        return np.divmod(self._get_pm, other)
    
    def __rdivmod__(self, other):
        return np.divmod(other, self._get_pm)
    
    def __mod__(self, other):
        return self._get_pm % other
    
    def __rmod__(self, other):
        return other % self._get_pm
    
    def __pow__(self, other):
        return self._get_pm ** other
    
    def __rpow__(self, other):
        return other ** self._get_pm
    
    @property
    def shape(self):
        return self._get_pm.shape
    
    @property
    def T(self):
        return self._get_pm.T
    
    @property
    def weight(self):
        return self._weight

    @property
    def entropy_interval(self):
        """Used just for WebLogo API calls"""
        return None

    @property
    def length(self):
        return self.width

    @property
    def entropy(self):
        return self.ic

    @property
    def counts(self):
        if self._counts is None:
            self.counts = (getattr(self, "_{}".format(self._pm_type)) * 100).astype(np.int64).values
        return self._counts

    @counts.setter
    def counts(self, counts):
        self._counts = counts

    @classmethod
    def __dir__(cls):
        """Just used to clean up the attributes and methods shown when `dir()` is called"""
        return sorted(cls.__all__)

    @staticmethod
    def _generate_consensus(pm):
        if pm is not None:
            return ''.join(pm.idxmax(axis=1))

    @staticmethod
    def _generate_ic(pm):
        if pm is not None:
            return _row_wise_ic(pm)

    @staticmethod
    def _get_width(pm):
        return pm.shape[0]

    @property
    def consensus(self):
        return self._consensus

    @property
    def ic(self):
        return self._ic

    @property
    def width(self):
        return self._width
    
    @property
    def alphabet_type(self):
        return self._alphabet_type

    @property
    def alphabet(self):
        if self._alphabet is None:
            if self.alphabet_type in utils._NA_ALPHABETS or self.alphabet_type in utils._AA_ALPHABETS:
                return utils._IDX_LETTERS[self.alphabet_type]
            elif self.alphabet_type == 'custom':
                raise ValueError("'custom' alphabet_type selected, but no alphabet was supplied")
        return self._alphabet

    @property
    def entropy(self):
        """Used just for WebLogo API call. Corrects for their conversion rate"""
        return self.ic / (1/np.log(2))

    @property
    def length(self):
        return self.width
    
    @property
    def pm(self):
        return self._get_pm
    
    @pm.setter
    def pm(self, pm_filename_or_array, pm_type = 'ppm', alphabet_type = 'DNA', alphabet = None):
        self._update_pm(pm_filename_or_array, pm_type, alphabet_type, alphabet)
    
    @property
    def background(self):
        return self._background
    
    @background.setter
    def background(self, background):
        self._background = background


class Ppm(Pm):
    """Main class for handling Position Probability Matrices (PPM).

    A PPM differs from a Position Frequency Matrix in that instead of counts for
    a given letter, the normalized weight is already calculated.

    This class automatically generates the consensus sequence for a given `alphabet`. 
    It also calculates the Information Content (IC) for each position.

    Attributes:
        ppm (`pandas.DataFrame`): PPM DataFrame generated by user-submitted PPM
        consensus (str): The consensus sequence determined by the PPM
        ic (`numpy.ndarray`): The information content for each position
        width (int): Length of the sequence/motif
        length (int): an alias for `width`
        alphabet_type (str): Desired alphabet type to use. (default: 'DNA')
        alphabet (str): Desired alphabet to use. Order matters (default: None)
        weight (`numpy.array`): 1-D array of ones. Used for WebLogo compatability. If the chosen
                alphabet type allows gaps, will base weights on gap average in that position
        counts (`pandas.DataFrame`): Counts of letters at the given position. If
                `counts` is not supplied (because PPM was the entry-point), the PPM will be cast
                as a PFM by multiplying it by 100
        pseudocount: some number to offset PPM values at to prevent -inf/+inf (default: 1e-10)
        background (Collection): must be an iterable with length of alphabet with each letter's respective respective background probability or constant. (default: for NA-0.25, for AA-Robinson-Robinson Frequencies)
    """
    
    __all__ =  ['ppm', 'consensus', 'ic', 'width', 'counts', 'background',
               'alphabet', 'alphabet_type', 'length', 'weight', 'pseudocount']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, pm_type='ppm', **kwargs)

    @classmethod
    def __dir__(cls):
        """Just used to clean up the attributes and methods shown when `dir()` is called"""
        return sorted(cls.__all__)
    
    @property
    def ppm(self):
        return self._get_pm
    
    @ppm.setter
    def ppm(self, ppm_filename_or_array, pm_type = 'ppm', alphabet_type = 'DNA', alphabet = None):
        super()._update_pm(ppm_filename_or_array, pm_type, alphabet_type, alphabet)
        

class Pfm(Pm):
    """Main class for handling Position Frequency Matrices (PFM).

    A Position Frequency Matrix contains the counts for a given letter at a given position

    This class automatically generates the consensus sequence for a given `alphabet`. 

    Attributes:
        pfm (`pandas.DataFrame`): PFM DataFrame generated by user-submitted PFM
        consensus (str): The consensus sequence determined by the PFM
        width (int): Length of the sequence/motif
        length (int): an alias for `width`
        alphabet_type (str): Desired alphabet type to use. (default: 'DNA')
        alphabet (str): Desired alphabet to use. Order matters (default: None)
        weight (`numpy.array`): 1-D array of ones. Used for WebLogo compatability. If the chosen
                alphabet type allows gaps, will base weights on gap average in that position
        counts (`pandas.DataFrame`): Synonym for pfm
    """
    
    __all__ =  ['pfm', 'consensus', 'width', 'counts', 'alphabet', 'alphabet_type', 'length', 'weight', 'background']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, pm_type='pfm', **kwargs)

    @classmethod
    def __dir__(cls):
        """Just used to clean up the attributes and methods shown when `dir()` is called"""
        return sorted(cls.__all__)
    
    @property
    def pfm(self):
        return self._get_pm
    
    @pfm.setter
    def pfm(self, pfm_filename_or_array, pm_type = 'pfm', alphabet_type = 'DNA', alphabet = None):
        super()._update_pm(pfm_filename_or_array, pm_type, alphabet_type, alphabet)
        

class Pwm(Pm):
    """Main class for handling Position Weight Matrices (PWM).

    A PWM differs from a Position Frequency Matrix in that instead of counts for
    a given letter, the normalized weight is already calculated.

    This class automatically generates the consensus sequence for a given `alphabet` and PWM. It also calculates the Information Content (IC) for each position.

    Attributes:
        pwm (`pandas.DataFrame`): PWM DataFrame generated by user-submitted PWM
        consensus (str): The consensus sequence determined by the PWM
        ic (`numpy.ndarray`): The information content for each position
        width (int): Length of the sequence/motif
        length (int): an alias for `width`
        alphabet_type (str): Desired alphabet type to use. (default: 'DNA')
        alphabet (str): Desired alphabet to use. Order matters (default: None)
        weight (`numpy.array`): 1-D array of ones. Used for WebLogo compatability. If the chosen
                alphabet type allows gaps, will base weights on gap average in that position
        counts (`pandas.DataFrame`): Counts of letters at the given position. If
                `counts` is not supplied (because PPM was the entry-point), the PPM will be cast
                as a PFM by multiplying it by 100
        pseudocount: some number to offset PPM values at to prevent -inf/+inf (default: 1e-10)
        background (Collection): must be an iterable with length of alphabet with each letter's respective respective background probability or constant. (default: for NA-0.25, for AA-Robinson-Robinson Frequencies)
    """
    
    __all__ =  ['pwm', 'consensus', 'ic', 'width', 'counts', 'background',
               'alphabet', 'alphabet_type', 'length', 'weight', 'pseudocount']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, pm_type='pwm', **kwargs)

    @classmethod
    def __dir__(cls):
        """Just used to clean up the attributes and methods shown when `dir()` is called"""
        return sorted(cls.__all__)
    
    @property
    def pwm(self):
        return self._get_pm
    
    @pwm.setter
    def pwm(self, pwm_filename_or_array, pm_type = 'pwm', alphabet_type = 'DNA', alphabet = None):
        super()._update_pm(pwm_filename_or_array, pm_type, alphabet_type, alphabet)
        

@singledispatch
def _submit_pm(pm_matrix):
    raise TypeError('pm_filename_or_array` must be a filename, `np.ndarray`, `pd.DataFrame`, or `Pm`')


@_submit_pm.register
def _(pm_matrix: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(data = pm_matrix)


@_submit_pm.register(Pm)
@_submit_pm.register(pd.DataFrame)
def _(pm_matrix): 
    return pm_matrix


@_submit_pm.register
def _(pm_matrix: str) -> pd.DataFrame:
    if not os.path.isfile(pm_matrix):
        raise FileNotFoundError('{} was not found'.format(pm_matrix))
    if alphabet not in utils._IDX_LETTERS:
        raise ValueError('alphabet must be a version of DNA, RNA, or AA')

    return pd.read_table(pm_matrix, delim_whitespace = True, header = None, comment = '#')


def _check_background(pm, background = None, alphabet_type = "DNA", alphabet = None):
    """Just used to make sure background frequencies are acceptable or present"""
    
    # If the user supplied the background
    if background is not None:
        if not isinstance(background, Real):
            if not isinstance(background, Collection):
                raise ValueError("background must be an iterable with length of alphabet with each letter's respective respective background probability or constant")
            else:
                return background
        else:
             return background
    
    # Attempt to figure out the background data from existing information
    else:
        try:
            alph = pm.alphabet
        except AttributeError:
            if alphabet is not None:
                alph = alphabet
            else:
                alph = utils._IDX_LETTERS[alphabet_type]
        if isinstance(pm, Pm):
            if pm.alphabet_type in utils._NA_ALPHABETS:
                background = utils._NA_background
            elif pm.alphabet_type in utils._AA_ALPHABETS:
                background = utils._AA_background
            else:
                raise ValueError('alphabet type ({}) not supported by default backgrounds. Please provide your own'.format(pm.alphabet_type))
        elif isinstance(pm, pd.DataFrame):
            if alphabet_type in utils._NA_ALPHABETS:
                background = utils._NA_background
            elif alphabet_type in utils._AA_ALPHABETS:
                background = utils._AA_background
            else:
                raise ValueError('alphabet type ({}) not supported by default backgrounds. Please provide your own'.format(pm.alphabet_type))
        else:
            raise ValueError('provided position matrix must be of type Pm, Pfm, Ppm, or Pwm')
    # Have to make sure that the background is a constant or long enough to broadcast through the matrix
    if not isinstance(background, Real):
        assert len(alph) == len(background), 'Background must be of equal length of sequence or a constant'
    return np.array(list(background.values()))


def pwm2ppm(pwm, background = None, pseudocount = None):
    """Converts a Pwm to a ppm array

    Args:
        pwm (Pwm): a fully initialized Pwm
        background: accounts for relative weights from background. Must be a constant or same number of columns as Pwm (default: None)
        pseudocount (const): The number used to offset log-likelihood conversion from probabilites (default: None -> 1e-10)

    Returns:
        (np.array): converted values

    Raises:
        ValueError: if the pseudocount isn't a constant or the same length as sequence
    """
    background = _check_background(pwm, background)
    if pseudocount is not None:
        if not isinstance(pseudocount, Real) and len(pseudocount) != pwm.length:
            raise ValueError('pseudocount must be the same length as the sequence or a constant')
    else:
        pseudocount = 1e-10
    return _init_pm(np.power(2, pwm + np.log2(background)) - pseudocount, pm_type = 'ppm')
        

def ppm2pwm(ppm, background= None, pseudocount = None):
    """Converts a Ppm to a pwm array

    Args:
        ppm (Ppm): a fully initialized Ppm
        background: accounts for relative weights from background. Must be a constant or same number of columns as Pwm (default: None)
        pseudocount (const): The number used to offset log-likelihood conversion from probabilites (default: None -> 1e-10)

    Returns:
        (np.array): converted values

    Raises:
        ValueError: if the pseudocount isn't a constant or the same length as sequence
    """
    background = _check_background(ppm, background)
    if pseudocount is not None:
        if not isinstance(pseudocount, Real) and len(pseudocount) != ppm.length:
            raise ValueError('pseudocount must be the same length as the sequence or a constant')
    else:
        pseudocount = 1e-10
    return _init_pm(np.log2(ppm +  pseudocount) - np.log2(background), pm_type = 'pwm')


def ppm2pfm(ppm):
    """Converts a Ppm to a pfm array

    Args:
        ppm (Ppm): a fully initialized Ppm

    Returns:
        (np.array): converted values
    """
    return _init_pm((ppm * 100).astype(np.int64), pm_type = 'pfm')


def pfm2ppm(pfm):
    """Converts a Pfm to a ppm array

    Args:
        pfm (Pfm): a fully initialized Pfm

    Returns:
        (np.array): converted values
    """
    return _init_pm((pfm.T / pfm.sum(axis = 1)).T, pm_type = 'ppm')


def pfm2pwm(pfm, background = None, pseudocount = None):
    """Converts a Pfm to a pwm array

    Args:
        pfm (Pfm): a fully initialized Pfm
        background: accounts for relative weights from background. Must be a constant or same number of columns as Pwm (default: None)
        pseudocount (const): The number used to offset log-likelihood conversion from probabilites (default: None -> 1e-10)

    Returns:
        (np.array): converted values
    """
    return _init_pm(ppm2pwm(pfm2ppm(pfm), background, pseudocount), pm_type = 'pwm')


def pwm2pfm(pwm, background = None, pseudocount = None):
    """Converts a Pwm to a pfm array

    Args:
        pwm (Pwm): a fully initialized Pwm
        background: accounts for relative weights from background. Must be a constant or same number of columns as Pwm (default: None)
        pseudocount (const): The number used to offset log-likelihood conversion from probabilites (default: None -> 1e-10)

    Returns:
        (np.array): converted values
    """
    return _init_pm(ppm2pfm(pwm2ppm(pwm, background, pseudocount)), pm_type = 'pfm')


class CompletePM(Pm):
    """Final class of the seqlogo package.
    
    If the user supplies *any* PM structure (PFM, PPM, PWM), it will compute any missing values, to
    include information content, consensus, and weights.

    Attributes:
        pfm (pd.DataFrame): position frequency matrix. Calculated if missing if another is present
        ppm (pd.DataFrame): position probability matrix. Calculated if missing if another is present
        pwm (pd.DataFrame): position weight matrix. Calculated if missing if another is present
        ic (np.array): positional information content
        length (int): length of sequence
        width (int): synonym for `length`
        weight (np.array): array of weights (calculated if gapped, else just ones)
        counts (`numpy.ndarray` or `pandas.DataFrame` or `Pm`): count data for each letter
            at a given position. (default: None)
        alphabet_type (str): Desired alphabet to use. Order matters (default: 'DNA')
            "DNA" := "ACGT"
            "reduced DNA" := "ACGTN-"
            "ambig DNA" := "ACGTRYSWKMBDHVN-"
            "RNA" := "ACGU"
            "reduced RNA" := "ACGUN-"
            "ambig RNA" := "ACGURYSWKMBDHVN-"
            "AA" : = "ACDEFGHIKLMNPQRSTVWY"
            "reduced AA" := "ACDEFGHIKLMNPQRSTVWYX*-"
            "ambig AA" := "ACDEFGHIKLMNOPQRSTUVWYBJZX*-"
            "custom" := None
            (default: 'DNA')
        alphabet (str): if 'custom' is selected or a specialize alphabet is desired, this accepts a string (default: None)
        background (constant or Collection): Offsets used to calculate background letter probabilities (defaults: If 
            using an Nucleic Acid alphabet: 0.25; if using an Aminio Acid alphabet: Robinson-Robinson Frequencies)
        pseudocount (constant): Some constant to offset PPM conversion to PWM to prevent -/+ inf. (default: 1e-10)
    """
    
    __all__ = ['pm', 'pfm', 'ppm', 'pwm', 'consensus', 'ic', 'width', 'counts', 
               'alphabet', 'alphabet_type', 'length', 'weight']
    
    def __init__(self, pfm = None, ppm = None, pwm = None, background = None, pseudocount = None,
                 alphabet_type = 'DNA', alphabet = None, default_pm = 'ppm'):
        """Initializes the CompletePm

        Creates the CompletePm instance. If the user does not define any `pm_filename_or_array`,
        it will be initialized to empty. Will generate all other attributes as soon
        as a `pm_filename_or_array` is supplied.

        Args:
            pfm (str or `numpy.ndarray` or `pandas.DataFrame` or Pm): The user supplied
                PFM. If it is a filename, the file will be opened
                and parsed. If it is an `numpy.ndarray` or `pandas.DataFrame`,
                it will just be assigned. (default: None, skips '#' comment lines)
            ppm (str or `numpy.ndarray` or `pandas.DataFrame` or Pm): The user supplied
                PPM. If it is a filename, the file will be opened
                and parsed. If it is an `numpy.ndarray` or `pandas.DataFrame`,
                it will just be assigned. (default: None, skips '#' comment lines)
            pwm (str or `numpy.ndarray` or `pandas.DataFrame` or Pm): The user supplied
                PWM. If it is a filename, the file will be opened
                and parsed. If it is an `numpy.ndarray` or `pandas.DataFrame`,
                it will just be assigned. (default: None, skips '#' comment lines)
            background (constant or Collection): Offsets used to calculate background letter probabilities (defaults: If 
                using an Nucleic Acid alphabet: 0.25; if using an Aminio Acid alphabet: Robinson-Robinson Frequencies)
            pseudocount (constant): Some constant to offset PPM conversion to PWM to prevent -/+ inf. (defaults to 1e-10)
            alphabet_type (str): Desired alphabet to use. Order matters (default: 'DNA')
                "DNA" := "ACGT"
                "reduced DNA" := "ACGTN-"
                "ambig DNA" := "ACGTRYSWKMBDHVN-"
                "RNA" := "ACGU"
                "reduced RNA" := "ACGUN-"
                "ambig RNA" := "ACGURYSWKMBDHVN-"
                "AA" : = "ACDEFGHIKLMNPQRSTVWY"
                "reduced AA" := "ACDEFGHIKLMNPQRSTVWYX*-"
                "ambig AA" := "ACDEFGHIKLMNOPQRSTUVWYBJZX*-"
                "custom" := None
                (default: 'DNA')
            alphabet (str): if 'custom' is selected or a specialize alphabet is desired, this accepts a string (default: None)
            default_pm (str): which of the 3 pm's do you want to call '*home*'? (default: 'ppm')
        """
        self._pm = self._pfm = self._ppm = self._pwm = None
        self._weight = self._width = self._consensus = None
        self._counts = self._weight = self._ic = None
        self._alphabet_type = alphabet_type
        self._alphabet = alphabet
        self._pm_type = "cpm"
        self._default_pm = default_pm

        if pseudocount is None:
            self.pseudocount = 1e-10
        else:
            self.pseudocount = pseudocount
        if background is None:
            self.background = None
        else:
            self.background = background

        if any([pfm is not None, ppm is not None, pwm is not None]):
            self._update_pm(pfm, ppm, pwm, background, pseudocount, alphabet_type, alphabet)
        
    def _update_pm(self, pfm = None, ppm = None, pwm = None, background = None,
             pseudocount = None, alphabet_type = None, alphabet = None):
        if alphabet_type is None:
            alphabet_type = self.alphabet_type

        # Set the ones the user has provided
        if pfm is not None:
            if not isinstance(pfm, Pm):
                self._pfm = _init_pm(pfm, pm_type = 'pfm', alphabet_type = alphabet_type, alphabet = alphabet)
            else:
                self._pfm = pfm.pfm
        if ppm is not None:
            if not isinstance(ppm, Pm):
                self._ppm = _init_pm(ppm, pm_type = 'ppm', alphabet_type = alphabet_type, alphabet = alphabet)
            else:
                self._ppm = ppm.ppm
        if pwm is not None:
            if not isinstance(pfm, Pm):
                self._pwm = _init_pm(pwm, pm_type = 'pwm', alphabet_type = alphabet_type, alphabet = alphabet)
            else:
                self._pwm = pwm.pwm

        # Fill in the blanks
        if pfm is not None and ppm is None:
            self._ppm = pfm2ppm(self._pfm)

        if pfm is not None and pwm is None:
            self._pwm = pfm2pwm(self._pfm, background, pseudocount)

        if ppm  is not None and pfm is None:
            self._pfm = ppm2pfm(self._ppm)

        if ppm is not None and pwm is None:
            self._pwm = ppm2pwm(self._ppm, background, pseudocount)

        if pwm  is not None and pfm is None:
            self._pfm = pwm2pfm(self._pwm, background, pseudocount)

        if pwm  is not None and ppm is None:
            self._ppm = pwm2ppm(self._pwm, background, pseudocount)

        self._width = self._get_width(self._get_pm)
        if not isinstance(self.pseudocount, Real):
            if len(self.pseudocount) != self.width:
                raise ValueError('pseudocount must be the same length as sequence or a constant')
        if self._alphabet_type not in ("DNA", "RNA", "AA"):
            self._weight = self._get_pm[:,:-1].sum(axis=1)/self._get_pm.sum(axis=1)
        else:
            self._weight = np.ones((self.width,), dtype=np.int8)
        self._counts = self.pfm
        self._consensus = self._generate_consensus(self._get_pm)
        self.background = _check_background(self)
        self._ic = (self.ppm * self.pwm).sum(axis=1)
        (pwm2ppm(self.pwm, background = self.background, pseudocount = self.pseudocount) * self.pwm).sum(axis = 1)

    @property
    def counts(self):
        return self._counts.values

    @property
    def pfm(self):
        return self._pfm
    
    @pfm.setter
    def pfm(self, pfm_filename_or_array, pm_type = 'pfm', alphabet_type = 'DNA', alphabet = None):
        super()._update_pm(pfm_filename_or_array, pm_type, alphabet_type, alphabet)
    
    @property
    def ppm(self):
        return self._ppm
    
    @ppm.setter
    def ppm(self, ppm_filename_or_array, pm_type = 'ppm', alphabet_type = 'DNA', alphabet = None):
        super()._update_pm(ppm_filename_or_array, pm_type, alphabet_type, alphabet)
        
    @property
    def pwm(self):
        return self._pwm
    
    @pwm.setter
    def pwm(self, ppm_filename_or_array, pm_type = 'pwm', alphabet_type = 'DNA', alphabet = None):
        super()._update_pm(pwm_filename_or_array, pm_type, alphabet_type, alphabet)

    @classmethod
    def __dir__(cls):
        """Just used to clean up the attributes and methods shown when `dir()` is called"""
        return sorted(cls.__all__)

    @property
    def _get_pm(self):
        return getattr(self, "_{}".format(self._default_pm))