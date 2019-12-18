import os
import numpy as np
from scipy.special import hankel1
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import h5py


class PltToy2dac:
    def __init__(self, datadir, freqlist, nfast, nslow, dx,
                 npml, zsrc, zrec, xsrc, xrec, z0=0, x0=0, fastz=True):
        """
        Read and plot toy2dac forward modeling seismic data, spectrum, and wavefield
        :param datadir: string,
        :param freqlist: array-like,
        :param nfast: int, n in fast dimension of model
        :param nslow: int, n in slow dimension of model
        :param dx: float, spacing of model
        :param npml: int
        :param zsrc: array-like,
        :param zrec: array-like,
        :param xsrc: float,
        :param xrec: float,
        :param z0: float, z coord at uppler left corner of model
        :param x0: float, x coord at uppler left corner of model
        :param fastz: bool,
        """
        self.datadir = datadir
        self.freqlist = np.array(freqlist)
        self.npml = npml
        self.dx = dx
        self.n0 = nslow
        self.n1 = nfast
        self.z0 = z0
        self.x0 = x0
        self.zsrc = np.array(zsrc)
        self.zrec = np.array(zrec)
        self.xsrc = xsrc
        self.xrec = xrec
        self.fastz = fastz
        if fastz:
            self.height = (nfast - 1) * self.dx
            self.width = (nslow - 1) * self.dx
        else:
            self.width = (nfast - 1) * self.dx
            self.height = (nslow - 1) * self.dx

    def read_wavefield(self, fname='wavefield'):
        n0 = self.n0 + 2 * self.npml
        n1 = self.n1 + 2 * self.npml
        nfreq = len(self.freqlist)
        with open(os.path.join(self.datadir, fname), 'rb') as f:
            wf = np.fromfile(f, dtype=np.float32).reshape([nfreq, n0, n1])
        return wf

    def plot_wavefield(self, ifreq, fname='wavefield', perc=95):
        idx = np.where(ifreq == self.freqlist)[0]
        wf = self.read_wavefield(fname)
        img = wf[idx].T if self.fastz else wf[idx]
        img = np.squeeze(img)
        img = img[self.npml:-self.npml, self.npml:-self.npml]
        vmax = np.percentile(np.abs(img), perc)
        ext = (self.x0, self.x0 + self.width,
               self.z0 + self.height, self.z0)
        fig, ax = plt.subplots()
        ax.imshow(img, extent=ext, cmap='gray', vmin=-vmax, vmax=vmax)
        plt.show()

    def read_seis(self, fname):
        seis = np.fromfile(os.path.join(self.datadir, fname), dtype=np.complex64)
        nfreq = len(self.freqlist)
        nsrc = len(self.zsrc)
        nrec = len(self.zrec)
        seis = seis.reshape([nfreq, nsrc, nrec])
        return seis

    def plot_spec(self, fname, zsrc_plot, zrec_plot, vp=3000, qp=1000):
        seis = self.read_seis(fname)
        idSrc = np.argmin(np.abs(zsrc_plot - self.zsrc))
        idRec = np.argmin(np.abs(zrec_plot - self.zrec))
        trace = seis[:, idSrc, idRec]
        amp = np.absolute(trace)
        phase = np.unwrap(np.angle(trace))
        greenfunc = greenfunc2d((self.xsrc, self.zsrc[idSrc]),
                                (self.xrec, self.zrec[idRec]),
                                self.freqlist, vp, qp)
        amp_green = np.absolute(greenfunc)
        phase_green = np.unwrap(np.angle(greenfunc))
        fig, ax = plt.subplots(1, 2)
        ax[0].plot(self.freqlist, amp, 'b', label='Modeled')
        ax[0].plot(self.freqlist, amp_green, 'r', label='Theoretic')
        ax[0].set_xlabel('Freq [Hz]')
        ax[0].set_ylabel('Amp')
        ax[0].legend()
        ax[1].plot(self.freqlist, phase, 'b')
        ax[1].plot(self.freqlist, phase_green, 'r')
        ax[1].set_xlabel('Freq [Hz]')
        ax[1].set_ylabel('Phase [rad]')
        plt.show()

    def freq2time(self, fname, savename, fc, delay_n_period=10):
        """
        Read freq domain impluse response binary file;
        output hdf5 of freq and time domain data
        :param fname: string, freq domain impluse response binary file
        :param savename: string, hdf5 filename without extension
        :param fc: float, central freq
        :param delay_n_period: float,
        :return: hdf5 file with keys
            seismo: time domain data, source wavelet = ricker(fc, delay_n_period)
            seismo_spec: freq domain data, source wavelet = ricker(fc, delay_n_period)
            spectrum: freq domain impluse response
            delay:
            fc:
            df:
            dt:
            freqlist:
        """
        dataf = self.read_seis(fname)
        _, nsrc, nrec = dataf.shape
        fmax = self.freqlist.max()
        dfreq = self.freqlist[1] - self.freqlist[0]
        Nhalf = int(fmax / dfreq)
        N = 1 + 2 * Nhalf
        f = dfreq * np.roll(np.arange(-Nhalf, Nhalf + 1), -Nhalf)
        ind1 = int(self.freqlist[0] / dfreq)
        ind2 = Nhalf + 1
        datafft = np.zeros((N, nsrc, nrec), dtype=np.complex64)
        datafft[ind1:ind2, :, :] = dataf
        datafft[ind2:-ind1 + 1, :, :] = np.conj(dataf[::-1, :, :])
        rconst = np.sqrt(np.pi)
        delay = delay_n_period / fc
        ricker_delay = 2. / rconst * f ** 2 / fc ** 3 * np.exp(
            -(f / fc) ** 2 + 1j * 2 * np.pi * f * delay)
        for i in range(nsrc):
            for j in range(nrec):
                datafft[:, i, j] = ricker_delay * datafft[:, i, j]
        datat = -np.real(1./N * dfreq * np.fft.fftn(datafft, s=[N], axes=[0]))
        with h5py.File(os.path.join(self.datadir, savename + '.h5'), 'w') as f:
            f.create_dataset('seismo', data=datat)
            f.create_dataset('fc', data=fc)
            f.create_dataset('delay', data=delay)
            f.create_dataset('spectrum', data=dataf)
            f.create_dataset('seismo_spec', data=datafft[ind1:ind2, :, :])
            f.create_dataset('freqlist', data=self.freqlist)
            f.create_dataset('df', data=dfreq)
            f.create_dataset('dt', data=1./dfreq/(N-1))

    def plot_seismo(self, fname, fh5, zsrc_plot, zrec_plot, fc=100, delay_n_period=10):
        """
        Plot one trace of time domain data
        :param fname:
        :param fh5:
        :param zsrc_plot: float, src depth
        :param zrec_plot: float, rec depth
        :param fc: float, central freq
        :param delay_n_period: float, num of delayed periods
        :return:
        """
        if not os.path.exists(os.path.join(self.datadir, fh5 + '.h5')):
            self.freq2time(fname, fh5, fc, delay_n_period)
        with h5py.File(os.path.join(self.datadir, fh5 + '.h5'), 'r') as f:
            seis = f['seismo'][()]
            dt = f['dt'][()]
            delay = f['delay'][()]
            fc = f['fc'][()]
        nt = seis.shape[0]
        ntPlot = nt
        t = dt * np.arange(ntPlot) * 1000
        idSrc = np.argmin(np.abs(zsrc_plot - self.zsrc))
        idRec = np.argmin(np.abs(zrec_plot - self.zrec))
        trace = seis[:ntPlot, idSrc, idRec]
        fig, ax = plt.subplots()
        ax.plot(t, trace)
        ax.set_xlabel('t [ms]')
        ax.set_title('zsrc = {:g} [m]\n'
                     ' delay = {:g} [ms], fc = {:g} Hz'.format(
            self.zsrc[idSrc], delay * 1000, fc))
        print('zsrc = {:g} [m], xsrc = {:g} [m] \n'
              'zrec = {:g} [m], xrec = {:g} [m]'.format(
               self.zsrc[idSrc], self.xsrc, self.zrec[idRec], self.xrec))
        plt.show()

    def plot_gather(self, fname, fh5, zsrc_plot, zrec_plot=(0, 106), t_plot=(0, 1000),
                    fc=100, delay_n_period=10, aspect=1.0, figsize=(6, 6), clip=1., interp_scalar=1):
        """
        Plot a shot gather a gray scale image
        :param fname:
        :param fh5:
        :param zsrc_plot:
        :param zrec_plot:
        :param t_plot:
        :param fc:
        :param delay_n_period:
        :param aspect:
        :param figsize:
        :param clip:
        :param interp_scalar:
        :return:
        """
        if not os.path.exists(os.path.join(self.datadir, fh5 + '.h5')):
            self.freq2time(fname, fh5, fc, delay_n_period)
        with h5py.File(os.path.join(self.datadir, fh5 + '.h5'), 'r') as f:
            seis = f['seismo'][()]
            dt = f['dt'][()]
            delay = f['delay'][()]
        nt = seis.shape[0]
        t = (dt * np.arange(nt) - delay) * 1000
        idSrc = np.argmin(np.abs(zsrc_plot - self.zsrc))
        idRec0 = np.argmin(np.abs(zrec_plot[0] - self.zrec))
        idRec1 = np.argmin(np.abs(zrec_plot[1] - self.zrec))
        idt0 = np.argmin(np.abs(t_plot[0] - t))
        idt1 = np.argmin(np.abs(t_plot[1] - t))
        data = seis[idt0:idt1 + 1, idSrc, idRec0:idRec1 + 1]
        if interp_scalar > 1:
            data = self.interp_seis(t[idt0:idt1+1], data, interp_scalar)
        amp_max = np.max(np.abs(data))
        vmin = -clip * amp_max
        vmax = clip * amp_max
        data_plot = np.clip(data, vmin, vmax)
        ext = [self.zrec[idRec0], self.zrec[idRec1], t[idt1], t[idt0]]
        fig, ax = plt.subplots(figsize=figsize)
        img = ax.imshow(data, extent=ext, cmap='Greys', aspect=aspect, vmin=vmin, vmax=vmax)
        # polarity: black is positive
        # ax.imshow(data, cmap='Greys')
        ax.set_ylabel('t (ms)')
        ax.set_xlabel('zrec (m)')
        # divider = make_axes_locatable(ax)
        # cax = divider.append_axes('right', size='5%', pad=0.05)
        # cbar = fig.colorbar(img, cax=cax, spacing='uniform')
        plt.tight_layout()
        plt.show()
        return fig, ax

    def interp_seis(self, t, data, scalar=5.):
        """
        Interpolate data for display
        :param t:
        :param data:
        :param scalar:
        :return:
        """
        dt0 = t[1] - t[0]
        dt = dt0 / scalar
        tplot = np.arange(t[0], t[-1] + 0.5 * dt, dt)
        ntrace = data.shape[1]
        data_out = np.zeros([len(tplot), ntrace])
        for i in range(ntrace):
            data_out[:, i] = np.interp(tplot, t, data[:, i])
        return data_out

    def plot_wiggle(self, fname, fh5, zsrc_plot, zrec_plot=(0, 106), t_plot=(0, 1000),
                    fc=100, delay_n_period=10, figsize=(6, 6), clip=0.9):
        """
        Plot seismogram as wiggles
        :param fname: string, binary file of freq domain data
        :param fh5: string, hdf5 file of time domain data
        :param zsrc_plot:
        :param zrec_plot:
        :param t_plot:
        :param fc:
        :param delay_n_period:
        :param figsize:
        :param clip:
        :return:
        """
        if not os.path.exists(os.path.join(self.datadir, fh5 + '.h5')):
            self.freq2time(fname, fh5, fc, delay_n_period)
        with h5py.File(os.path.join(self.datadir, fh5 + '.h5'), 'r') as f:
            seis = f['seismo'][()]
            dt = f['dt'][()]
            delay = f['delay'][()]
        nt = seis.shape[0]
        t = (dt * np.arange(nt) - delay) * 1000
        idSrc = np.argmin(np.abs(zsrc_plot - self.zsrc))
        idRec0 = np.argmin(np.abs(zrec_plot[0] - self.zrec))
        idRec1 = np.argmin(np.abs(zrec_plot[1] - self.zrec))
        idt0 = np.argmin(np.abs(t_plot[0] - t))
        idt1 = np.argmin(np.abs(t_plot[1] - t))
        data = seis[idt0:idt1 + 1, idSrc, idRec0:idRec1 + 1]
        fig, ax = plt.subplots(figsize=figsize)
        ntrace = idRec1 - idRec0 + 1
        offsets = np.arange(1, 1 + ntrace, 1)
        taxis = t[idt0:idt1+1]
        amp_max = np.max(data)
        scalar = 1 / amp_max
        data_plot = data * scalar
        for i in range(ntrace):
            offset = offsets[i]
            x = offset + data_plot[:, i]
            ax.plot(x, taxis, 'k-')
            ax.fill_betweenx(taxis, offset, x, where=(x > offset), color='k')
        ax.set_ylabel('t [ms]')
        ax.set_xlabel('trace NO.')
        ax.set_ylim(ax.get_ylim()[::-1])
        plt.show()
        return fig, ax

    def get_id(self, x, xarr):
        idx = np.argmin(np.abs(x - xarr))
        return idx

    def get_spec(self, fh5, ricker=True):
        key = 'seismo_spec' if ricker else 'spectrum'
        with h5py.File(os.path.join(self.datadir, fh5 + '.h5'), 'r') as f:
            trace = f[key][()]
        amp = np.absolute(trace)
        phase = np.unwrap(np.angle(trace))
        return amp, phase

    def get_spec_trace(self, fh5, zsrc_plot, zrec_plot, ricker=True):
        amp, phase = self.get_spec(fh5, ricker)
        idSrc = self.get_id(zsrc_plot, self.zsrc)
        idRec = self.get_id(zrec_plot, self.zrec)
        data_amp = amp[:, idSrc, idRec]
        data_phase = phase[:, idSrc, idRec]
        return data_amp, data_phase


def greenfunc2d(xzsrc, xzrec, freqlist, vp, qp=1000):
    xzsrc = np.array(xzsrc)
    xzrec = np.array(xzrec)
    freq = np.array(freqlist)
    r = np.sqrt(np.sum((xzsrc - xzrec)**2))
    vp = vp * (1 - 1j/(2 * qp))
    k = 2 * np.pi * freq / vp
    g = hankel1(0, k * r) * 1j/4
    return g