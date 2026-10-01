"""Numerical checks for one-plane calibration, angle conventions and rejection gates."""
import math
import unittest
from calibration_core import Measurement, Calibration, phasor, summarize, calibrate, correction


class CalibrationTests(unittest.TestCase):
    def settings(self, sign=1):
        return dict(profile='Rotor A', reference='Marca del cubo', direction='Horario',phase_sign=sign,
                    target_rpm=1800.,tolerance_pct=2.,stability_pct=10.,vref=3.3,
                    sample_rate=2000.,threshold=2048,source_kind='serial')

    def test_known_unbalance_and_angular_sign(self):
        for sign in (1,-1):
            alpha=phasor(.002,35)
            u0=phasor(250,sign*80)
            trial=phasor(100,sign*20)
            initial=Measurement(alpha*u0,1800,.00001,3)
            weighted=Measurement(alpha*(u0+trial),1800,.00001,3)
            c=calibrate(initial,weighted,mass=1,radius=100,angle=20,**self.settings(sign))
            self.assertAlmostEqual(abs(c.alpha-alpha),0,places=10)
            result=correction(initial,c,50)
            self.assertAlmostEqual(result['mass_g'],5,places=10)
            self.assertAlmostEqual(result['angle_deg'],260,places=10)
            self.assertAlmostEqual(abs(u0+phasor(result['mass_g']*50,sign*result['angle_deg'])),0,places=9)
            self.assertEqual(Calibration.from_dict(c.to_dict()),c)

    def test_circular_mean(self):
        m=summarize([(1,359,1800),(1,0,1800),(1,1,1800)],1800,2,10)
        self.assertAlmostEqual(math.degrees(math.atan2(m.vector.imag,m.vector.real)),0,places=8)

    def test_reject_invalid_calibration_and_readings(self):
        m=Measurement(1+0j,1800,.01,3)
        with self.assertRaises(ValueError):calibrate(m,m,mass=1,radius=100,angle=0,**self.settings())
        with self.assertRaises(ValueError):summarize([(1,0,2000)]*3,1800,2,10)
        with self.assertRaises(ValueError):summarize([(1,0,1800),(1,120,1800),(1,240,1800)],1800,2,10)
        c=calibrate(m,Measurement(2+0j,1800,.01,3),mass=1,radius=100,angle=0,**self.settings())
        data=c.to_dict();data['alpha_real']=float('nan')
        with self.assertRaises(ValueError):Calibration.from_dict(data)
        with self.assertRaises(ValueError):correction(m,c,0)
        with self.assertRaises(ValueError):correction(Measurement(1+0j,2100,0,3),c,100)


if __name__=='__main__':unittest.main()
