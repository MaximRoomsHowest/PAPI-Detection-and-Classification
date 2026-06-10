import albumentations as A


def weather_transform():
    return A.OneOf([
        A.RandomRain(
            slant_range=(-10, 10),
            drop_length=15,
            drop_width=1,
            blur_value=3,
            brightness_coefficient=0.9,
            p=1.0,
        ),
        A.RandomFog(
            fog_coef_range=(0.05, 0.2),
            alpha_coef=0.08,
            p=1.0,
        ),
        A.RandomShadow(p=1.0),
        A.RandomSunFlare(p=1.0),
    ], p=0.25)