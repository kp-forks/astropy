"""
Normalization class for Matplotlib that can be used to produce
colorbars.
"""

import inspect

import numpy as np
from numpy import ma

from astropy.utils.compat.optional_deps import HAS_MATPLOTLIB
from astropy.utils.decorators import deprecated_renamed_argument

from .interval import (
    AsymmetricPercentileInterval,
    BaseInterval,
    ManualInterval,
    MinMaxInterval,
    PercentileInterval,
)
from .stretch import (
    AsinhStretch,
    BaseStretch,
    LinearStretch,
    LogStretch,
    PowerStretch,
    SinhStretch,
    SqrtStretch,
)

if HAS_MATPLOTLIB:
    from matplotlib.colors import Normalize
else:

    class Normalize:
        def __init__(self, *args, **kwargs):
            raise ImportError("matplotlib is required in order to use this class.")


__all__ = ["ImageNormalize", "SimpleNorm", "imshow_norm", "simple_norm"]

__doctest_requires__ = {"*": ["matplotlib"]}


class ImageNormalize(Normalize):
    """
    Normalization class to be used with Matplotlib.

    Parameters
    ----------
    data : ndarray, optional
        The image array.  This input is used only if ``interval`` is
        also input.  ``data`` and ``interval`` are used to compute the
        vmin and/or vmax values only if ``vmin`` or ``vmax`` are not
        input.
    interval : `~astropy.visualization.BaseInterval` subclass instance, optional
        The interval object to apply to the input ``data`` to determine
        the ``vmin`` and ``vmax`` values.  This input is used only if
        ``data`` is also input.  ``data`` and ``interval`` are used to
        compute the vmin and/or vmax values only if ``vmin`` or ``vmax``
        are not input.
    vmin, vmax : float, optional
        The minimum and maximum levels to show for the data.  The
        ``vmin`` and ``vmax`` inputs override any calculated values from
        the ``interval`` and ``data`` inputs.
    stretch : `~astropy.visualization.BaseStretch` subclass instance
        The stretch object to apply to the data.  The default is
        `~astropy.visualization.LinearStretch`.
    clip : bool, optional
        If `True`, data values outside the [0:1] range are clipped to
        the [0:1] range.
    invalid : None or float, optional
        Value to assign NaN values generated by this class.  NaNs in the
        input ``data`` array are not changed.  For matplotlib
        normalization, the ``invalid`` value should map to the
        matplotlib colormap "under" value (i.e., any finite value < 0).
        If `None`, then NaN values are not replaced.  This keyword has
        no effect if ``clip=True``.

    Notes
    -----
    If ``vmin == vmax``, the input data will be mapped to 0.
    """

    def __init__(
        self,
        data: np.ndarray | None = None,
        interval: BaseInterval | None = None,
        vmin: float | None = None,
        vmax: float | None = None,
        stretch: BaseStretch = LinearStretch(),
        clip: bool = False,
        invalid: float | None = -1.0,
    ):
        # this super call checks for matplotlib
        super().__init__(vmin=vmin, vmax=vmax, clip=clip)

        self.vmin = vmin
        self.vmax = vmax

        if stretch is None:
            raise ValueError("stretch must be input")
        if not isinstance(stretch, BaseStretch):
            raise TypeError("stretch must be an instance of a BaseStretch subclass")
        self.stretch = stretch

        if interval is not None and not isinstance(interval, BaseInterval):
            raise TypeError("interval must be an instance of a BaseInterval subclass")
        self.interval = interval

        self.inverse_stretch = stretch.inverse
        self.clip = clip
        self.invalid = invalid

        # Define vmin and vmax if not None and data was input
        if data is not None:
            self._set_limits(data)

    def _set_limits(self, data):
        if self.vmin is not None and self.vmax is not None:
            return

        # Define vmin and vmax from the interval class if not None
        if self.interval is None:
            if self.vmin is None:
                self.vmin = np.min(data[np.isfinite(data)])
            if self.vmax is None:
                self.vmax = np.max(data[np.isfinite(data)])
        else:
            _vmin, _vmax = self.interval.get_limits(data)
            if self.vmin is None:
                self.vmin = _vmin
            if self.vmax is None:
                self.vmax = _vmax

    def __call__(self, values, clip=None, invalid=None):
        """
        Transform values using this normalization.

        Parameters
        ----------
        values : array-like
            The input values.
        clip : bool, optional
            If `True`, values outside the [0:1] range are clipped to the
            [0:1] range.  If `None` then the ``clip`` value from the
            `ImageNormalize` instance is used (the default of which is
            `False`).
        invalid : None or float, optional
            Value to assign NaN values generated by this class.  NaNs in
            the input ``data`` array are not changed.  For matplotlib
            normalization, the ``invalid`` value should map to the
            matplotlib colormap "under" value (i.e., any finite value <
            0).  If `None`, then the `ImageNormalize` instance value is
            used.  This keyword has no effect if ``clip=True``.
        """
        if clip is None:
            clip = self.clip

        if invalid is None:
            invalid = self.invalid

        if isinstance(values, ma.MaskedArray):
            if clip:
                mask = False
            else:
                mask = values.mask
            values = values.filled(self.vmax)
        else:
            mask = False

        # Make sure scalars get broadcast to 1-d
        if np.isscalar(values):
            values = np.array([values], dtype=float)
        else:
            # copy because of in-place operations after
            values = np.array(values, copy=True, dtype=float)

        # Define vmin and vmax if not None
        self._set_limits(values)

        if self.vmin == self.vmax:
            values *= 0.0
        elif self.vmin > self.vmax:
            raise ValueError("vmin must be less than or equal to vmax")
        else:
            # Normalize based on vmin and vmax
            np.subtract(values, self.vmin, out=values)
            np.true_divide(values, self.vmax - self.vmin, out=values)

            # Clip to the 0 to 1 range
            if clip:
                values = np.clip(values, 0.0, 1.0, out=values)

            # Stretch values
            if self.stretch._supports_invalid_kw:
                values = self.stretch(values, out=values, clip=False, invalid=invalid)
            else:
                values = self.stretch(values, out=values, clip=False)

        # Convert to masked array for matplotlib
        return ma.array(values, mask=mask)

    def inverse(self, values, invalid=None):
        # Find unstretched values in range 0 to 1
        if self.inverse_stretch._supports_invalid_kw:
            values_norm = self.inverse_stretch(values, clip=False, invalid=invalid)
        else:
            values_norm = self.inverse_stretch(values, clip=False)

        # Scale to original range
        return values_norm * (self.vmax - self.vmin) + self.vmin


class SimpleNorm:
    """
    Class to create a normalization object that can be used for
    displaying images with Matplotlib.

    This convenience class provides the most common image stretching
    functions. Additional stretch functions are available in
    `~astropy.visualization.mpl_normalize.ImageNormalize`.

    Parameters
    ----------
    stretch : {'linear', 'sqrt', 'power', log', 'asinh', 'sinh'}, optional
        The stretch function to apply to the image. The default is
        'linear'.

    percent : float, optional
        The percentage of the image values used to determine the pixel
        values of the minimum and maximum cut levels. The lower cut
        level will set at the ``(100 - percent) / 2`` percentile, while
        the upper cut level will be set at the ``(100 + percent) / 2``
        percentile. The default is 100.0. ``percent`` is ignored if
        either ``min_percent`` or ``max_percent`` is input.

    min_percent : float, optional
        The percentile value used to determine the pixel value of
        minimum cut level. The default is 0.0. ``min_percent`` overrides
        ``percent``.

    max_percent : float, optional
        The percentile value used to determine the pixel value of
        maximum cut level. The default is 100.0. ``max_percent``
        overrides ``percent``.

    vmin : float, optional
        The pixel value of the minimum cut level. Data values less
        than ``vmin`` will set to ``vmin`` before stretching the
        image. The default is the image minimum. ``vmin`` overrides
        ``min_percent``.

    vmax : float, optional
        The pixel value of the maximum cut level. Data values greater
        than ``vmax`` will set to ``vmax`` before stretching the
        image. The default is the image maximum. ``vmax`` overrides
        ``max_percent``.

    power : float, optional
        The power index for ``stretch='power'``. The default is 1.0.

    log_a : float, optional
        The log index for ``stretch='log'``. The default is 1000.

    asinh_a : float, optional
        For ``stretch='asinh'``, the value where the asinh curve
        transitions from linear to logarithmic behavior, expressed as a
        fraction of the normalized image. Must be in the range between 0
        and 1. The default is 0.1.

    sinh_a : float, optional
        The scaling parameter for ``stretch='sinh'``. The default is
        0.3.

    clip : bool, optional
        If `True`, data values outside the [0:1] range are clipped to
        the [0:1] range.

    invalid : None or float, optional
        Value to assign NaN values generated by the normalization. NaNs
        in the input ``data`` array are not changed. For matplotlib
        normalization, the ``invalid`` value should map to the
        matplotlib colormap "under" value (i.e., any finite value < 0).
        If `None`, then NaN values are not replaced. This keyword has no
        effect if ``clip=True``.

    See Also
    --------
    simple_norm

    Examples
    --------
    .. plot::
        :include-source:

        import numpy as np
        import matplotlib.pyplot as plt
        from astropy.visualization import SimpleNorm

        image = np.arange(65536).reshape((256, 256))
        snorm = SimpleNorm('sqrt', percent=98)
        norm = snorm(image)
        fig, ax = plt.subplots()
        axim = ax.imshow(image, norm=norm, origin='lower')
        fig.colorbar(axim)
    """

    def __init__(
        self,
        stretch="linear",
        percent=None,
        *,
        min_percent=None,
        max_percent=None,
        vmin=None,
        vmax=None,
        power=1.0,
        log_a=1000,
        asinh_a=0.1,
        sinh_a=0.3,
        clip=False,
        invalid=-1.0,
    ):
        if percent is not None:
            interval = PercentileInterval(percent)
        elif min_percent is not None or max_percent is not None:
            interval = AsymmetricPercentileInterval(
                lower_percentile=min_percent, upper_percentile=max_percent
            )
        elif vmin is not None or vmax is not None:
            interval = ManualInterval(vmin, vmax)
        else:
            interval = MinMaxInterval()
        self.interval = interval

        if stretch == "linear":
            stretch = LinearStretch()
        elif stretch == "sqrt":
            stretch = SqrtStretch()
        elif stretch == "power":
            stretch = PowerStretch(power)
        elif stretch == "log":
            stretch = LogStretch(log_a)
        elif stretch == "asinh":
            stretch = AsinhStretch(asinh_a)
        elif stretch == "sinh":
            stretch = SinhStretch(sinh_a)
        else:
            raise ValueError(f"Unknown stretch: {stretch}.")
        self.stretch = stretch

        self.clip = clip
        self.invalid = invalid

    def __call__(self, data):
        """
        Return an `ImageNormalize` instance that can be used for displaying
        images with Matplotlib.

        Parameters
        ----------
        data : ndarray
            The image array.

        Returns
        -------
        result : `ImageNormalize` instance
            An `ImageNormalize` instance that can be used for
            displaying images with Matplotlib.
        """
        vmin, vmax = self.interval.get_limits(data)
        return ImageNormalize(
            vmin=vmin,
            vmax=vmax,
            stretch=self.stretch,
            clip=self.clip,
            invalid=self.invalid,
        )

    def imshow(self, data, ax=None, **kwargs):
        """
        A convenience function to display an image using matplotlib's
        `matplotlib.pyplot.imshow` function with the normalization
        defined by this class.

        Parameters
        ----------
        data : 2D or 3D array-like
            The data to display. Can be whatever
            `~matplotlib.pyplot.imshow` and `ImageNormalize` both
            accept.

        ax : None or `~matplotlib.axes.Axes`, optional
            The matplotlib axes on which to plot. If `None`, then the
            current `~matplotlib.axes.Axes` instance is used.

        **kwargs : dict, optional
            Keywords arguments passed to `~matplotlib.pyplot.imshow`.
            Cannot include the ``norm`` or ``X`` keyword.

        Returns
        -------
        result : `~matplotlib.image.AxesImage`
            The `~matplotlib.image.AxesImage` generated by
            `~matplotlib.pyplot.imshow`.

        Examples
        --------
        .. plot::
            :include-source:

            import numpy as np
            import matplotlib.pyplot as plt
            from astropy.visualization import SimpleNorm

            image = np.arange(65536).reshape((256, 256))
            snorm = SimpleNorm('sqrt', percent=98)
            fig, ax = plt.subplots()
            axim = snorm.imshow(image, ax=ax, origin='lower')
            fig.colorbar(axim)
        """
        import matplotlib.pyplot as plt

        if ax is None:
            ax = plt.gca()

        if "norm" in kwargs:
            raise ValueError(
                "This class already defines the norm. Use "
                "matplotlib.pyplot.imshow directly to use your norm."
            )

        axim = ax.imshow(data, norm=self(data), **kwargs)
        return axim


@deprecated_renamed_argument(["min_cut", "max_cut"], ["vmin", "vmax"], ["6.1", "6.1"])
def simple_norm(
    data,
    stretch="linear",
    power=1.0,
    asinh_a=0.1,
    vmin=None,
    vmax=None,
    min_percent=None,
    max_percent=None,
    percent=None,
    clip=False,
    log_a=1000,
    invalid=-1.0,
    sinh_a=0.3,
):
    """
    Return a Normalization class that can be used for displaying images
    with Matplotlib.

    This function enables only a subset of image stretching functions
    available in `~astropy.visualization.mpl_normalize.ImageNormalize`.

    This function is used by the
    ``astropy.visualization.scripts.fits2bitmap`` script.

    Parameters
    ----------
    data : ndarray
        The image array.

    stretch : {'linear', 'sqrt', 'power', log', 'asinh', 'sinh'}, optional
        The stretch function to apply to the image. The default is
        'linear'.

    power : float, optional
        The power index for ``stretch='power'``. The default is 1.0.

    asinh_a : float, optional
        For ``stretch='asinh'``, the value where the asinh curve
        transitions from linear to logarithmic behavior, expressed as a
        fraction of the normalized image. Must be in the range between 0
        and 1. The default is 0.1.

    vmin : float, optional
        The pixel value of the minimum cut level. Data values less
        than ``vmin`` will set to ``vmin`` before stretching the
        image. The default is the image minimum. ``vmin`` overrides
        ``min_percent``.

    vmax : float, optional
        The pixel value of the maximum cut level. Data values greater
        than ``vmax`` will set to ``vmax`` before stretching the image.
        The default is the image maximum. ``vmax`` overrides

    min_percent : float, optional
        The percentile value used to determine the pixel value of
        minimum cut level. The default is 0.0. ``min_percent`` overrides
        ``percent``.

    max_percent : float, optional
        The percentile value used to determine the pixel value of
        maximum cut level. The default is 100.0. ``max_percent``
        overrides ``percent``.

    percent : float, optional
        The percentage of the image values used to determine the pixel
        values of the minimum and maximum cut levels. The lower cut
        level will set at the ``(100 - percent) / 2`` percentile, while
        the upper cut level will be set at the ``(100 + percent) / 2``
        percentile. The default is 100.0. ``percent`` is ignored if
        either ``min_percent`` or ``max_percent`` is input.

    clip : bool, optional
        If `True`, data values outside the [0:1] range are clipped to
        the [0:1] range.

    log_a : float, optional
        The log index for ``stretch='log'``. The default is 1000.

    invalid : None or float, optional
        Value to assign NaN values generated by the normalization. NaNs
        in the input ``data`` array are not changed. For matplotlib
        normalization, the ``invalid`` value should map to the
        matplotlib colormap "under" value (i.e., any finite value < 0).
        If `None`, then NaN values are not replaced. This keyword has no
        effect if ``clip=True``.

    sinh_a : float, optional
        The scaling parameter for ``stretch='sinh'``. The default is
        0.3.

    Returns
    -------
    result : `ImageNormalize` instance
        An `ImageNormalize` instance that can be used for displaying
        images with Matplotlib.

    See Also
    --------
    SimpleNorm
    """
    simple_norm = SimpleNorm(
        stretch=stretch,
        percent=percent,
        min_percent=min_percent,
        max_percent=max_percent,
        vmin=vmin,
        vmax=vmax,
        power=power,
        log_a=log_a,
        asinh_a=asinh_a,
        sinh_a=sinh_a,
        clip=clip,
        invalid=invalid,
    )
    return simple_norm(data)


# used in imshow_norm
_norm_sig = inspect.signature(ImageNormalize)


def imshow_norm(data, ax=None, **kwargs):
    """A convenience function to call matplotlib's `matplotlib.pyplot.imshow`
    function, using an `ImageNormalize` object as the normalization.

    Parameters
    ----------
    data : 2D or 3D array-like
        The data to show. Can be whatever `~matplotlib.pyplot.imshow` and
        `ImageNormalize` both accept. See `~matplotlib.pyplot.imshow`.
    ax : None or `~matplotlib.axes.Axes`, optional
        If None, use pyplot's imshow.  Otherwise, calls ``imshow`` method of
        the supplied axes.
    **kwargs : dict, optional
        All other keyword arguments are parsed first by the
        `ImageNormalize` initializer, then to
        `~matplotlib.pyplot.imshow`.

    Returns
    -------
    result : tuple
        A tuple containing the `~matplotlib.image.AxesImage` generated
        by `~matplotlib.pyplot.imshow` as well as the `ImageNormalize`
        instance.

    Notes
    -----
    The ``norm`` matplotlib keyword is not supported.

    Examples
    --------
    .. plot::
        :include-source:

        import numpy as np
        import matplotlib.pyplot as plt
        from astropy.visualization import (imshow_norm, MinMaxInterval,
                                           SqrtStretch)

        # Generate and display a test image
        image = np.arange(65536).reshape((256, 256))
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        im, norm = imshow_norm(image, ax, origin='lower',
                               interval=MinMaxInterval(),
                               stretch=SqrtStretch())
        fig.colorbar(im)
    """
    if ax is None:
        if not HAS_MATPLOTLIB:
            raise ModuleNotFoundError("matplotlib is required for imshow norm")

        import matplotlib.pyplot as plt

        ax = plt.gca()

    if "norm" in kwargs:
        raise ValueError(
            "There is no point in using imshow_norm if you give "
            "the ``norm`` keyword - use imshow directly if you "
            "want that."
        )

    imshow_kwargs = dict(kwargs)

    norm_kwargs = {"data": data}
    for pname in _norm_sig.parameters:
        if pname in kwargs:
            norm_kwargs[pname] = imshow_kwargs.pop(pname)

    imshow_kwargs["norm"] = ImageNormalize(**norm_kwargs)
    imshow_result = ax.imshow(data, **imshow_kwargs)

    return imshow_result, imshow_kwargs["norm"]
