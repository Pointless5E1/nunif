# Random noise for Photo, made at random.
import math
import random
from torchvision import transforms as T
from torchvision.transforms import (
    functional as TF,
    InterpolationMode,
)
import torch
from nunif.utils.perlin2d import generate_perlin_noise_2d
from nunif.utils import blend as B


def random_crop(x, size):
    i, j, h, w = T.RandomCrop.get_params(x, size)
    x = TF.crop(x, i, j, h, w)
    return x


def random_mask_8x8(x, noise):
    assert x.shape == noise.shape
    h = x.shape[1] // 8 + 1
    w = x.shape[2] // 8 + 1
    p = random.uniform(0.02, 0.5)
    mask = torch.bernoulli(torch.torch.full((1, h, w), p))
    method = random.choice([0, 1, 2])
    if method == 0:
        mask = TF.resize(mask, (mask.shape[1] * 8, mask.shape[2] * 8),
                         interpolation=InterpolationMode.NEAREST, antialias=True)
    elif method == 1:
        mask = TF.resize(mask, (mask.shape[1] * 2, mask.shape[2] * 2),
                         interpolation=InterpolationMode.NEAREST, antialias=True)
        mask = TF.resize(mask, (mask.shape[1] * 4, mask.shape[2] * 4),
                         interpolation=InterpolationMode.BILINEAR, antialias=True)
    elif method == 2:
        mask = TF.resize(mask, (mask.shape[1] * 4, mask.shape[2] * 4),
                         interpolation=InterpolationMode.NEAREST, antialias=True)
        mask = TF.resize(mask, (mask.shape[1] * 2, mask.shape[2] * 2),
                         interpolation=InterpolationMode.BILINEAR, antialias=True)
    mask = mask[:, :x.shape[1], :x.shape[2]]
    return torch.clamp(x * (1. - mask) + noise * mask, 0., 1.)


def gen_direction_kernel(ch):
    center = random.uniform(1 / 3., 0.99)
    side = (1. - center) * 0.5
    direction = random.choice([0, 1, 2, 3])
    kernel = torch.zeros((3, 3), dtype=torch.float32)
    kernel[1][1] = center
    if direction == 0:
        kernel[0][1] = side
        kernel[2][1] = side
    elif direction == 1:
        kernel[1][0] = side
        kernel[1][2] = side
    elif direction == 2:
        kernel[0][0] = side
        kernel[2][2] = side
    elif direction == 3:
        kernel[0][2] = side
        kernel[2][0] = side

    # assert math.isclose(kernel.sum().item(), 1., abs_tol=1e-4)
    kernel = kernel.reshape(1, 1, 3, 3)
    # for groups=ch
    kernel = kernel.expand((ch, 1, 3, 3))
    return kernel


def gen_noise_image(size, ch):
    h, w = size
    noise = torch.randn((ch, h, w))
    if random.uniform(0, 1) < 0.25:
        # blur noise
        if random.choice([True, False]):
            weight = gen_direction_kernel(ch)
            noise = torch.nn.functional.conv2d(
                noise.unsqueeze(0),
                weight=weight, stride=1, padding=1, groups=ch).squeeze(0)
        else:
            kernel_size = random.choice([3, 5])
            sigma = random.uniform(0.6, 1.4)
            noise = TF.gaussian_blur(noise, kernel_size=kernel_size, sigma=sigma)
    if random.uniform(0, 1) < 0.25:
        # dot masked noise
        p = random.uniform(0.1, 0.5)
        noise = noise * torch.bernoulli(torch.torch.full((1, noise.shape[1], noise.shape[2]), p))
    if random.uniform(0, 1) < 0.25:
        # random resize
        scale_h = random.uniform(1, 2)
        scale_w = random.uniform(1, 2)
        noise = TF.resize(noise, (int(noise.shape[1] * scale_h), int(noise.shape[2] * scale_w)),
                          interpolation=InterpolationMode.BILINEAR, antialias=True)
        noise = random_crop(noise, (h, w))

    return noise


def gaussian_noise_variants(x, strength=0.05):
    c, h, w = x.shape
    ch = 1 if random.uniform(0., 1.) < 0.5 else 3
    noise = gen_noise_image((h, w), ch)
    return torch.clamp(x + noise.expand(x.shape) * strength, 0., 1.)


def gaussian_8x8_masked_noise(x, strength=0.1):
    """
    I don't know what kind of noise this is,
    but it happens in old digital photos.
    (buggy JPEG encoder?)
    """
    c, h, w = x.shape
    noise = gen_noise_image((h, w), 1)
    if random.choice([True, False]):
        x = gaussian_noise_variants(x, strength=strength * 0.5)

    noise = x + noise.expand(x.shape) * strength
    return random_mask_8x8(x, noise)


def sampling_noise(x, sampling=8, strength=0.1):
    c, h, w = x.shape
    noise = torch.randn((sampling, h, w)).mean(dim=0, keepdim=True)
    m = random.choice([0, 1, 2])
    if m == 0:
        return torch.clamp(B.lighten(x, x + noise.expand(x.shape) * strength), 0., 1.)
    elif m == 1:
        return torch.clamp(B.darken(x, x + noise.expand(x.shape) * strength), 0., 1.)
    elif m == 2:
        return torch.clamp(x + noise.expand(x.shape) * strength, 0., 1.)


def grain_noise1(x, strength=0.1):
    c, h, w = x.shape
    alpha = [1., random.uniform(0, 1)]
    random.shuffle(alpha)
    ch = 1 if random.uniform(0., 1.) < 0.5 else 3
    noise1 = torch.randn((ch, h, w))
    noise2 = torch.randn((ch, h // 2, w // 2))
    interpolation = random.choice([InterpolationMode.BILINEAR, InterpolationMode.NEAREST])
    noise2 = TF.resize(noise2, (h, w),
                       interpolation=interpolation, antialias=True)
    noise = noise1 * alpha[0] + noise2 * alpha[1]
    max_v = torch.abs(noise).max() + 1e-6
    noise = noise / max_v
    return torch.clamp(x + noise.expand(x.shape) * strength, 0., 1.)


def grain_noise2(x, strength=0.15):
    c, h, w = x.shape
    size = max(w, h)
    antialias = random.choice([True, False])
    interpolation = random.choice([InterpolationMode.BILINEAR, InterpolationMode.NEAREST])
    use_rotate = random.choice([True, False])
    if use_rotate:
        bs = math.ceil(size * math.sqrt(2))
        res = random.choice([1, 2])
        ps = bs // res
        ps += 4 - ps % 4
        ns = ps * res * 2
        noise = generate_perlin_noise_2d([ns, ns], [ps, ps]).unsqueeze(0)
        noise = TF.rotate(noise, angle=random.randint(0, 360), interpolation=interpolation)
        noise = TF.center_crop(noise, (int(noise.shape[1] / math.sqrt(2)), int(noise.shape[2] / math.sqrt(2))))
        scale = random.uniform(1., noise.shape[1] / size)
        crop_h = int(h * scale)
        crop_w = int(w * scale)
    else:
        bs = size
        res = random.choice([1, 2])
        ps = bs // res
        ps += 4 - ps % 4
        ns = ps * res * 2
        noise = generate_perlin_noise_2d([ns, ns], [ps, ps]).unsqueeze(0)
        keep_aspect = random.uniform(0, 1) < 0.8
        if keep_aspect:
            scale = random.uniform(1., noise.shape[1] / size)
            crop_h = int(h * scale)
            crop_w = int(w * scale)
        else:
            scale_h = random.uniform(1., noise.shape[1] / size)
            scale_w = random.uniform(1., noise.shape[1] / size)
            crop_h = int(h * scale_h)
            crop_w = int(w * scale_w)

    noise = random_crop(noise, (crop_h, crop_w))
    noise = TF.resize(noise, (h, w), interpolation=interpolation, antialias=antialias)
    return torch.clamp(x + noise.expand(x.shape) * strength, 0., 1.)


NR_RATE = {
    0: 0.1,
    1: 0.1,
    2: 0.5,
    3: 1,
}
STRENGTH_FACTOR = {
    0: 0.25,
    1: 0.5,
    2: 1.0,
    3: 1.0,
}


class RandomPhotoNoiseX():
    def __init__(self, noise_level, force=False):
        assert noise_level in {0, 1, 2, 3}
        self.noise_level = noise_level
        self.force = force

    def __call__(self, x, y):
        if not self.force:
            if random.uniform(0, 1) > NR_RATE[self.noise_level]:
                # do nothing
                return x, y

        x = TF.to_tensor(x)
        method = random.choice([0, 1, 2, 3])
        if method == 0:
            strength = random.uniform(0.02, 0.1) * STRENGTH_FACTOR[self.noise_level]
            x = sampling_noise(x, strength=strength)
        elif method == 1:
            strength = random.uniform(0.02, 0.1) * STRENGTH_FACTOR[self.noise_level]
            x = grain_noise1(x, strength=strength)
        elif method == 2:
            strength = random.uniform(0.02, 0.15) * STRENGTH_FACTOR[self.noise_level]
            x = grain_noise2(x, strength=strength)
        elif method == 3:
            if random.choice([True, False]):
                strength = random.uniform(0.02, 0.1) * STRENGTH_FACTOR[self.noise_level]
                x = gaussian_noise_variants(x, strength=strength)
            else:
                strength = random.uniform(0.02, 0.1) * STRENGTH_FACTOR[self.noise_level]
                x = gaussian_8x8_masked_noise(x, strength=strength)
        x = TF.to_pil_image(x)
        return x, y


def add_validation_noise(x, noise_level, index):
    def _add_gaussian_noise(x, strength):
        x = TF.to_tensor(x)
        x = torch.clamp(x + torch.randn((1, x.shape[1], x.shape[2])) * strength, 0., 1.)
        x = TF.to_pil_image(x)
        return x
    if noise_level in {0, 1}:
        if index % 10 == 0:
            x = _add_gaussian_noise(x, 0.05 * STRENGTH_FACTOR[noise_level])
    elif noise_level == 2:
        if index % 2 == 0:
            x = _add_gaussian_noise(x, 0.05 * STRENGTH_FACTOR[noise_level])
    elif noise_level == 3:
        x = _add_gaussian_noise(x, 0.05 * STRENGTH_FACTOR[noise_level])
    return x


def _test():
    from nunif.utils import pil_io
    import argparse
    import cv2

    def show(name, im):
        cv2.imshow(name, pil_io.to_cv2(im))

    def print_mean_diff(name, a, b):
        a = pil_io.to_tensor(a)
        b = pil_io.to_tensor(b)
        print(name, abs(a.mean().item() - b.mean().item()))

    def show_op(func, a):
        b = pil_io.to_image(func(pil_io.to_tensor(a)))
        print_mean_diff(func.__name__, a, b)
        show(func.__name__, b)

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--input", "-i", type=str, required=True, help="input file")
    args = parser.parse_args()
    im, _ = pil_io.load_image_simple(args.input)

    show_op(sampling_noise, im)
    show_op(grain_noise1, im)
    show_op(grain_noise2, im)
    show_op(gaussian_noise_variants, im)
    show_op(gaussian_8x8_masked_noise, im)

    cv2.waitKey(0)


def _test_gaussian():
    from nunif.utils import pil_io
    import argparse
    import cv2

    def show(name, im):
        cv2.imshow(name, pil_io.to_cv2(im))

    def show_op(func, a):
        show(func.__name__, pil_io.to_image(func(pil_io.to_tensor(a))))

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--input", "-i", type=str, required=True, help="input file")
    args = parser.parse_args()
    im, _ = pil_io.load_image_simple(args.input)

    while True:
        show_op(gaussian_noise, im)
        c = cv2.waitKey(0)
        if c in {ord("q"), ord("x")}:
            break


if __name__ == "__main__":
    _test()
    # _test_gaussian()
