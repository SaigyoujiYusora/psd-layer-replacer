from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage
import functools
import logging
import time
import psutil
import os

logging.basicConfig(level=logging.INFO)
logging.getLogger('psd_tools.psd.image_resources').setLevel(logging.ERROR)
logging.getLogger('psd_tools.psd.tagged_blocks').setLevel(logging.ERROR)


def profile_resources(func):
    def wrapper(*args, **kwargs):
        # 获取当前进程
        process = psutil.Process(os.getpid())

        # 记录初始内存和CPU使用情况
        start_memory = process.memory_info().rss / 1024 ** 2  # 以MB为单位
        start_cpu_time = process.cpu_times()
        start_time = time.time()  # 记录初始时间

        # 执行函数
        result = func(*args, **kwargs)

        # 记录结束内存和CPU使用情况
        end_memory = process.memory_info().rss / 1024 ** 2
        end_cpu_time = process.cpu_times()
        end_time = time.time()

        # 输出资源消耗
        print(f"函数 '{func.__name__}' 执行时间: {end_time - start_time:.4f} 秒")
        print(f"内存增加: {end_memory - start_memory:.4f} MB")
        print(f"用户CPU时间: {end_cpu_time.user - start_cpu_time.user:.4f} 秒")
        print(f"系统CPU时间: {end_cpu_time.system - start_cpu_time.system:.4f} 秒")

        return result

    return wrapper


def get_time(log=True, log_level=logging.INFO):
    def decorator(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            s_time = time.time()
            res = f(*args, **kwargs)
            e_time = time.time()
            elapsed_time = e_time - s_time
            if log:
                logging.log(log_level, '函数 {}耗时：{:.4f}秒'.format(f.__name__, elapsed_time))
            return res

        return inner

    return decorator


# @get_time()
def process_layer(psd, replacements, final_image, psd_size=None):
    global temp_index
    if psd_size is None:
        psd_size = psd.size
    for layer in psd:
        # 递归处理组
        if layer.is_group() and layer.is_visible():
            final_image = process_layer(layer, replacements, final_image, psd_size=psd_size)
        else:
            layer_image = layer.composite().convert("RGBA")

            if layer.name in replacements and layer.is_visible():

                if type(replacements[layer.name]) is not str:
                    if type(replacements[layer.name]) is int:
                        # 获取蒙版百分比
                        mask_percent = replacements[layer.name]

                        # 获取蒙版
                        mask = layer.mask.topil()
                        mask = mask.convert("L")

                        # 编辑蒙版
                        draw_mask = ImageDraw.Draw(mask)
                        draw_mask.rectangle([0, 0, mask.width, mask.height * (mask_percent / 100)], fill=0)

                        # 创建一个与PSD大小相同的空白图像，并将替换后的图像粘贴到目标图层的位置
                        replacement_layer = Image.new("RGBA", psd_size)
                        replacement_layer.paste(layer_image, layer.offset)

                        # 创建一个与裁剪图像大小相同的透明图像
                        alpha = Image.new("L", replacement_layer.size, 0)

                        position = layer.mask.bbox[:2]  # (x0, y0)
                        # 将蒙版数据粘贴到 alpha 图像上
                        alpha.paste(mask, position)

                        # 将 alpha 应用于裁剪后的图像
                        replacement_layer = Image.composite(replacement_layer,
                                                            Image.new("RGBA", psd_size, (0, 0, 0, 0)), alpha)

                        final_image = Image.alpha_composite(final_image, replacement_layer)

                        continue
                    elif type(replacements[layer.name]) is bool:
                        if replacements[layer.name]:
                            pass
                        else:
                            continue
                    elif type(replacements[layer.name]) is list:
                        # 创建一个与PSD大小相同的空白图像
                        replacement_layer = Image.new("RGBA", psd_size)

                        # 新建文字图层
                        text_layer = Image.new("RGBA", layer.size)
                        draw = ImageDraw.Draw(text_layer)
                        fontstyle = ImageFont.truetype(replacements[layer.name][1], replacements[layer.name][2])
                        draw.text((0, 0), half_width_to_full_width(replacements[layer.name][0]), fill=(0, 0, 0, 255),
                                  font=fontstyle)

                        # 将文字图层粘贴到目标图层的位置
                        replacement_layer.paste(text_layer, layer.offset)

                        # 将修改后的图层叠加到最终图像上
                        final_image = Image.alpha_composite(final_image, replacement_layer)
                        continue

                new_image_path = replacements[layer.name]
                new_image = Image.open(new_image_path).convert("RGBA")

                new_image_resized = new_image.resize(layer.size)

                # 创建一个与PSD大小相同的空白图像，并将替换后的图像粘贴到目标图层的位置
                replacement_layer = Image.new("RGBA", psd_size)
                replacement_layer.paste(new_image_resized, layer.offset)

                # 处理蒙版
                if layer.mask:
                    # 蒙版位置
                    bbox = layer.mask.bbox
                    position = (bbox[0], bbox[1])  # (x0, y0)
                    # size = (bbox[2] - bbox[0], bbox[3] - bbox[1])  # (width, height)
                    size = (bbox[2] - bbox[0], bbox[3] - bbox[1])  # (width, height)
                    # 获取蒙版的 alpha 通道数据
                    mask_data = layer.mask.topil()
                    mask_data = mask_data.convert("L")

                    # 创建一个与裁剪图像大小相同的透明图像
                    alpha = Image.new("L", replacement_layer.size, 0)

                    # 粘贴蒙版
                    alpha.paste(mask_data, position)

                    # 将 alpha 应用于裁剪后的图像
                    # replacement_layer.putalpha(alpha)
                    replacement_layer = Image.composite(replacement_layer, Image.new("RGBA", psd_size, (0, 0, 0, 0)),
                                                        alpha)

                final_image = Image.alpha_composite(final_image, replacement_layer)

            else:
                # 保留其他图层
                layer_temp = Image.new("RGBA", psd_size)
                layer_temp.paste(layer_image, layer.offset)
                final_image = Image.alpha_composite(final_image, layer_temp)

    return final_image


def half_width_to_full_width(text):
    # 半角转全角
    rstring = ""
    for t_char in text:
        inside_code = ord(t_char)
        if inside_code == 32:  # 半角空格
            inside_code = 12288
        elif 32 <= inside_code <= 126:
            inside_code += 65248

        rstring += chr(inside_code)
    return rstring


# @get_time()
@profile_resources
def draw_frame():
    import warnings
    warnings.filterwarnings("ignore", module="psd_tools")

    psd_path = 'final_lite.psd'
    # psd_path = 'text_test.psd'
    psd = PSDImage.open(psd_path)
    layer_name = ["UI_Chara_1", "UI_Chara_2", "UI_Chara_3"]
    new_image_path = "UI_Chara_3.png"
    layer_path = "top/All_chara/chara/1/chara/UI_Chara_405404"

    final_image = Image.new("RGBA", psd.size)

    # 图层替换定义
    replacements = {
        "User_Name": ["我去是舞萌痴AA","SEGA_MARUGOTHICDB.ttf",21.33],
        "UI_Chara_1": "UI_Chara_1.png",
        "UI_Chara_2": "UI_Chara_2.png",
        "UI_Chara_3": "UI_Chara_3.png",
        "background": "bg.png",
        "UI_Icon_image": "UI_Icon.png",
        "UI_Plate_409501": "UI_Plate.png",
        "Leader_Star_Color": 50,
        "Leader_Star_MAX": False
    }
    final_image = process_layer(psd, replacements, final_image)


    final_image.save("output.png")

draw_frame()

