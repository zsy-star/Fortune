"""测试 order_parser 订单文本解析器。

覆盖：
- 斜杠简写 01/10
- 纯数字列表 1,2,3各10
- 单生肖 兔各20
- 波色 红波各10
- 半波 红单各10
- 大小 大各10
- 单双 单各10
- 尾数 尾1各10
- 头数 1头各10
- 合数单双 合单各10
- 合数大小 合大各10
- 五行 金各10
- 澳门前缀
- 香港前缀
- 连肖
- 多生肖
- 全包
- 多行解析
- 空文本
- 非法号码
- 0金额
- 负金额
- 非法金额
- amount 与 total 语义
- ParseResult 字段兼容性
"""

from __future__ import annotations

import pytest

from services.order_parser import ParseResult, format_result, parse_lines, parse_order


# ======================================================================
# 斜杠简写
# ======================================================================


class TestSlashShorthand:
    """01/10 格式。"""

    def test_valid_slash(self) -> None:
        r = parse_order("01/10")
        assert r.success
        assert r.numbers == (1,)
        assert r.amount == 10.0
        assert r.total == 10.0
        assert r.category == "单号投注"

    def test_slash_out_of_range(self) -> None:
        r = parse_order("50/10")
        assert not r.success
        assert "超出范围" in r.error

    def test_slash_zero(self) -> None:
        r = parse_order("0/10")
        assert not r.success

    def test_macau_slash(self) -> None:
        r = parse_order("澳门01/10")
        assert r.success
        assert r.region == "澳门"
        assert r.numbers == (1,)

    def test_hk_slash(self) -> None:
        r = parse_order("香港49/5")
        assert r.success
        assert r.region == "香港"
        assert r.numbers == (49,)
        assert r.amount == 5.0


# ======================================================================
# 纯数字列表
# ======================================================================


class TestNumberList:
    """逗号分隔数字列表。"""

    def test_comma_separated(self) -> None:
        r = parse_order("1,2,3各10")
        assert r.success
        assert r.numbers == (1, 2, 3)
        assert r.amount == 10.0
        assert r.total == 30.0
        assert r.category == "纯数字"

    def test_with_leading_zeros(self) -> None:
        r = parse_order("01,02,03各5")
        assert r.success
        assert r.numbers == (1, 2, 3)
        assert r.amount == 5.0
        assert r.total == 15.0

    def test_space_separated(self) -> None:
        r = parse_order("1 2 3 4各10")
        assert r.success
        assert r.numbers == (1, 2, 3, 4)
        assert r.total == 40.0

    def test_chinese_comma(self) -> None:
        r = parse_order("1，2，3各10")
        assert r.success
        assert r.numbers == (1, 2, 3)

    def test_mixed_separators(self) -> None:
        r = parse_order("1, 5, 10, 15各10")
        assert r.success
        assert 1 in r.numbers and 10 in r.numbers

    def test_out_of_range_in_list(self) -> None:
        r = parse_order("1,50,3各10")
        assert not r.success
        assert "无法识别" in r.error or "类" in r.error

    def test_negative_in_list(self) -> None:
        r = parse_order("1,-2,3各10")
        assert not r.success


# ======================================================================
# 单生肖
# ======================================================================


class TestSingleZodiac:
    """单生肖解析。"""

    def test_tu_rabbit(self) -> None:
        r = parse_order("兔各20")
        assert r.success
        assert r.numbers == (4, 16, 28, 40)
        assert r.amount == 20.0
        assert r.total == 80.0
        assert r.category == "兔"

    def test_zodiac_long_name(self) -> None:
        r = parse_order("卯兔各10")
        assert r.success
        assert r.category == "兔"
        assert r.numbers == (4, 16, 28, 40)

    def test_zodiac_branch_name(self) -> None:
        r = parse_order("卯各10")
        assert r.success
        assert r.category == "兔"

    def test_ma_horse(self) -> None:
        r = parse_order("马各5")
        assert r.success
        assert r.numbers == (1, 13, 25, 37, 49)
        assert r.total == 25.0

    def test_shu_rat(self) -> None:
        r = parse_order("鼠各12")
        assert r.success
        assert r.numbers == (7, 19, 31, 43)


# ======================================================================
# 波色
# ======================================================================


class TestWaveColor:
    def test_red_wave(self) -> None:
        r = parse_order("红波各10")
        assert r.success
        assert r.category == "红波"
        assert 1 in r.numbers and 13 in r.numbers and 49 not in r.numbers
        assert r.amount == 10.0

    def test_blue_wave(self) -> None:
        r = parse_order("蓝波各10")
        assert r.success
        assert r.category == "蓝波"
        assert 3 in r.numbers

    def test_green_wave(self) -> None:
        r = parse_order("绿波各10")
        assert r.success
        assert r.category == "绿波"
        assert 5 in r.numbers


# ======================================================================
# 半波
# ======================================================================


class TestHalfWave:
    def test_red_odd(self) -> None:
        r = parse_order("红单各10")
        assert r.success
        assert r.category == "红单"
        assert 1 in r.numbers
        assert 2 not in r.numbers

    def test_red_even(self) -> None:
        r = parse_order("红双各10")
        assert r.success
        assert r.category == "红双"
        assert 2 in r.numbers

    def test_blue_odd(self) -> None:
        r = parse_order("蓝单各10")
        assert r.success
        assert r.category == "蓝单"

    def test_blue_even(self) -> None:
        r = parse_order("蓝双各10")
        assert r.success
        assert r.category == "蓝双"

    def test_green_odd(self) -> None:
        r = parse_order("绿单各10")
        assert r.success
        assert r.category == "绿单"

    def test_green_even(self) -> None:
        r = parse_order("绿双各10")
        assert r.success
        assert r.category == "绿双"


# ======================================================================
# 大小
# ======================================================================


class TestSize:
    def test_big(self) -> None:
        r = parse_order("大各10")
        assert r.success
        assert r.category == "大"
        for n in r.numbers:
            assert n >= 25
        assert len(r.numbers) == 25  # 25-49

    def test_small(self) -> None:
        r = parse_order("小各10")
        assert r.success
        assert r.category == "小"
        for n in r.numbers:
            assert n <= 24
        assert len(r.numbers) == 24  # 1-24


# ======================================================================
# 单双
# ======================================================================


class TestParity:
    def test_odd(self) -> None:
        r = parse_order("单各10")
        assert r.success
        assert r.category == "单"
        for n in r.numbers:
            assert n % 2 == 1

    def test_even(self) -> None:
        r = parse_order("双各10")
        assert r.success
        assert r.category == "双"
        for n in r.numbers:
            assert n % 2 == 0


# ======================================================================
# 尾数
# ======================================================================


class TestTail:
    def test_tail_1(self) -> None:
        r = parse_order("尾1各10")
        assert r.success
        assert r.category == "尾1"
        for n in r.numbers:
            assert n % 10 == 1
        assert 1 in r.numbers and 11 in r.numbers and 41 in r.numbers

    def test_tail_9(self) -> None:
        r = parse_order("尾9各5")
        assert r.success
        assert r.category == "尾9"
        for n in r.numbers:
            assert n % 10 == 9

    def test_tail_prefix(self) -> None:
        r = parse_order("0尾各10")
        assert r.success
        assert r.category == "尾0"


# ======================================================================
# 头数
# ======================================================================


class TestHead:
    def test_head_1(self) -> None:
        r = parse_order("1头各10")
        assert r.success
        assert r.category == "1头"
        for n in r.numbers:
            assert 10 <= n <= 19

    def test_head_2(self) -> None:
        r = parse_order("2头各5")
        assert r.success
        assert r.category == "2头"
        for n in r.numbers:
            assert 20 <= n <= 29

    def test_head_4(self) -> None:
        r = parse_order("4头各10")
        assert r.success
        assert r.category == "4头"
        for n in r.numbers:
            assert 40 <= n <= 49


# ======================================================================
# 合数单双
# ======================================================================


class TestCompositeParity:
    def test_he_dan(self) -> None:
        r = parse_order("合单各10")
        assert r.success
        assert r.category == "合单"

    def test_he_shuang(self) -> None:
        r = parse_order("合双各10")
        assert r.success
        assert r.category == "合双"


# ======================================================================
# 合数大小
# ======================================================================


class TestCompositeSize:
    def test_he_da(self) -> None:
        r = parse_order("合大各10")
        assert r.success
        assert r.category == "合大"

    def test_he_xiao(self) -> None:
        r = parse_order("合小各10")
        assert r.success
        assert r.category == "合小"


# ======================================================================
# 五行
# ======================================================================


class TestFiveElements:
    def test_jin(self) -> None:
        r = parse_order("金各10")
        assert r.success
        assert r.category == "金"

    def test_mu(self) -> None:
        r = parse_order("木各10")
        assert r.success
        assert r.category == "木"

    def test_shui(self) -> None:
        r = parse_order("水各10")
        assert r.success
        assert r.category == "水"

    def test_huo(self) -> None:
        r = parse_order("火各10")
        assert r.success
        assert r.category == "火"

    def test_tu(self) -> None:
        r = parse_order("土各10")
        assert r.success
        assert r.category == "土"


# ======================================================================
# 地域前缀
# ======================================================================


class TestRegionPrefix:
    def test_macau_prefix(self) -> None:
        r = parse_order("澳门兔各10")
        assert r.success
        assert r.region == "澳门"
        assert r.category == "兔"

    def test_hk_prefix(self) -> None:
        r = parse_order("香港兔各10")
        assert r.success
        assert r.region == "香港"

    def test_no_prefix(self) -> None:
        r = parse_order("兔各10")
        assert r.success
        assert r.region == ""


# ======================================================================
# 连肖
# ======================================================================


class TestLianXiao:
    def test_explicit_lian(self) -> None:
        r = parse_order("连兔龙蛇各10")
        assert r.success
        assert r.category == "连肖"
        assert len(r.zodiac_groups) == 3
        assert r.zodiac_groups[0][0] == "兔"
        assert r.zodiac_groups[1][0] == "龙"
        assert r.zodiac_groups[2][0] == "蛇"

    def test_explicit_tuo(self) -> None:
        r = parse_order("拖马虎各5")
        assert r.success
        assert r.category in ("拖肖", "连肖")

    def test_tail_lianxiao_pattern(self) -> None:
        r = parse_order("猪羊马三托各10")
        assert r.success
        assert "肖" in r.category

    def test_tail_lian(self) -> None:
        r = parse_order("鼠牛虎二连各10")
        assert r.success
        assert "肖" in r.category

    def test_tail_you(self) -> None:
        r = parse_order("马虎有各10")
        assert r.success
        assert "肖" in r.category


# ======================================================================
# 多生肖
# ======================================================================


class TestMultiZodiac:
    def test_multi_no_keyword(self) -> None:
        r = parse_order("兔龙蛇各10")
        assert r.success
        assert r.category == "多生肖"
        assert len(r.zodiac_groups) == 3

    def test_two_zodiacs(self) -> None:
        r = parse_order("马虎各5")
        assert r.success
        assert r.category == "多生肖"
        assert len(r.zodiac_groups) == 2


# ======================================================================
# 全包
# ======================================================================


class TestAllNumbers:
    def test_all_keyword(self) -> None:
        r = parse_order("全包各2")
        assert r.success
        assert r.category == "全包"
        assert len(r.numbers) == 49
        assert r.numbers[0] == 1
        assert r.numbers[-1] == 49
        assert r.amount == 2.0
        assert r.total == 98.0


# ======================================================================
# 多行解析
# ======================================================================


class TestMultiLine:
    def test_two_valid_lines(self) -> None:
        results = parse_lines("兔各10\n马各5")
        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].numbers == (4, 16, 28, 40)
        assert results[1].numbers == (1, 13, 25, 37, 49)

    def test_lines_with_blank(self) -> None:
        results = parse_lines("兔各10\n\n马各5\n")
        assert len(results) == 2

    def test_mixed_success(self) -> None:
        results = parse_lines("兔各10\n非法文本\n马各5")
        assert len(results) == 3
        assert results[0].success
        assert not results[1].success
        assert results[2].success


# ======================================================================
# 错误处理
# ======================================================================


class TestErrorHandling:
    def test_empty_text(self) -> None:
        r = parse_order("")
        assert not r.success
        assert "空" in r.error

    def test_whitespace_only(self) -> None:
        r = parse_order("   ")
        assert not r.success
        assert "空" in r.error

    def test_invalid_category(self) -> None:
        r = parse_order("xyz各10")
        assert not r.success
        assert "无法识别" in r.error

    def test_zero_amount(self) -> None:
        r = parse_order("兔各0")
        assert not r.success
        assert "金额必须大于 0" in r.error

    def test_negative_amount(self) -> None:
        r = parse_order("兔各-10")
        assert not r.success
        assert "金额必须大于 0" in r.error

    def test_invalid_amount_text(self) -> None:
        r = parse_order("兔各abc")
        assert not r.success
        assert ("格式无效" in r.error.lower()) or ("无法转为数字" in r.error)

    def test_no_separator(self) -> None:
        r = parse_order("兔")
        assert not r.success
        assert "各" in r.error or "分隔符" in r.error

    def test_no_category_before_separator(self) -> None:
        r = parse_order("各20")
        assert not r.success
        assert "类别" in r.error

    def test_out_of_range_slash(self) -> None:
        r = parse_order("99/10")
        assert not r.success


# ======================================================================
# 前缀剥离（订单标记等场景）
# ======================================================================


class TestPrefixStripping:
    """未知前缀自动跳过，不影响后续有效类别解析。"""

    def test_single_word_prefix_zodiac(self) -> None:
        r = parse_order("张三 兔各20")
        assert r.success
        assert r.category == "兔"
        assert r.numbers == (4, 16, 28, 40)
        assert r.amount == 20.0

    def test_single_word_prefix_number_list(self) -> None:
        r = parse_order("VIP 01,02,03各10")
        assert r.success
        assert r.category == "纯数字"
        assert r.numbers == (1, 2, 3)
        assert r.total == 30.0

    def test_multi_word_prefix(self) -> None:
        r = parse_order("客户A 标记 红波各10")
        assert r.success
        assert r.category == "红波"
        assert 1 in r.numbers

    def test_prefix_with_lianxiao(self) -> None:
        r = parse_order("张三 连兔龙蛇各10")
        assert r.success
        assert r.category == "连肖"
        assert len(r.zodiac_groups) == 3

    def test_prefix_before_macau_order(self) -> None:
        """地域前缀在开头才生效；订单标记在地域之后。"""
        r = parse_order("澳门 VIP 兔各10")
        assert r.success
        # 地域必须在最开头
        assert r.region == "澳门"
        # "VIP" 被前缀剥离，兔成功匹配
        assert r.category == "兔"

    def test_no_prefix_no_regression(self) -> None:
        """无前缀的正常输入不受影响。"""
        r = parse_order("兔各10")
        assert r.success
        assert r.category == "兔"

    def test_only_prefix_no_valid_category(self) -> None:
        """只有前缀没有有效类别时仍报错。"""
        r = parse_order("张三 李四各10")
        assert not r.success
        assert "无法识别" in r.error


# ======================================================================
# amount / total 语义
# ======================================================================


class TestAmountTotalSemantics:
    """amount = 每个号码的投注金额, total = amount × 号码数量。"""

    def test_single_number_slash(self) -> None:
        r = parse_order("01/10")
        assert r.amount == 10.0
        assert r.total == 10.0  # 单个号码

    def test_multi_number_list(self) -> None:
        r = parse_order("1,2,3各10")
        assert r.amount == 10.0  # 每号金额
        assert r.total == 30.0  # = 3 × 10

    def test_zodiac_class(self) -> None:
        r = parse_order("兔各20")
        assert r.amount == 20.0  # 每号金额
        assert r.total == 80.0  # = 4 × 20

    def test_big_class(self) -> None:
        r = parse_order("大各5")
        assert r.amount == 5.0
        assert r.total == 5.0 * 25  # 25 个号码

    def test_all_numbers(self) -> None:
        r = parse_order("全包各2")
        assert r.amount == 2.0
        assert r.total == 2.0 * 49  # 49 个号码

    def test_lianxiao(self) -> None:
        r = parse_order("连兔龙蛇各10")
        assert r.amount == 10.0
        # total = 10 × 合并去重后的号码数
        assert r.total == r.amount * len(r.numbers)


# ======================================================================
# ParseResult 字段兼容性
# ======================================================================


class TestParseResultFields:
    """所有字段必须保持。"""

    def test_all_fields_exist(self) -> None:
        r = parse_order("兔各10")
        # 核心字段
        assert hasattr(r, "success")
        assert isinstance(r.success, bool)
        assert hasattr(r, "category")
        assert isinstance(r.category, str)
        assert hasattr(r, "numbers")
        assert isinstance(r.numbers, tuple)
        assert hasattr(r, "amount")
        assert isinstance(r.amount, float)
        assert hasattr(r, "total")
        assert isinstance(r.total, float)
        assert hasattr(r, "error")
        assert isinstance(r.error, str)
        assert hasattr(r, "region")
        assert isinstance(r.region, str)
        assert hasattr(r, "zodiac_groups")
        assert isinstance(r.zodiac_groups, list)
        assert hasattr(r, "original_text")
        assert isinstance(r.original_text, str)

    def test_success_result_fields(self) -> None:
        r = parse_order("兔各10")
        assert r.success
        assert r.error == ""  # 成功时错误为空
        assert r.original_text == ""  # parse_order 不填，由调用方回填
        assert len(r.numbers) > 0

    def test_failure_result_fields(self) -> None:
        r = parse_order("各20")
        assert not r.success
        assert r.error != ""  # 失败时错误非空
        assert r.numbers == ()  # 默认空

    def test_region_only_macau_hk_or_empty(self) -> None:
        for text in ("兔各10", "澳门兔各10", "香港兔各10"):
            r = parse_order(text)
            assert r.region in ("澳门", "香港", "")

    def test_structure_unchanged(self) -> None:
        """ParseResult 仍可使用 dataclass 字段赋值。"""
        r = ParseResult(
            success=True,
            category="测试",
            numbers=(7,),
            amount=5.0,
            total=5.0,
            region="香港",
            zodiac_groups=[("马", (7,))],
        )
        assert r.success
        assert r.category == "测试"
        assert r.region == "香港"


# ======================================================================
# 格式化输出
# ======================================================================


class TestReverseZodiac:
    """反向查询：号码 → 生肖。"""

    def test_single_zodiac_match(self) -> None:
        r = parse_order("4,16,28,40各10")
        assert r.success
        output = format_result(r)
        assert "→" in output
        assert "兔(04,16,28,40)" in output

    def test_mixed_zodiacs(self) -> None:
        r = parse_order("1,2,3各10")  # 马, 蛇, 龙
        assert r.success
        output = format_result(r)
        assert "马(01)" in output
        assert "蛇(02)" in output
        assert "龙(03)" in output

    def test_zodiac_category_no_reverse(self) -> None:
        """生肖类别（非纯数字）不附加反向查询。"""
        r = parse_order("兔各10")
        assert r.success
        output = format_result(r)
        assert "→" not in output


class TestFormatResult:
    def test_success_format(self) -> None:
        r = parse_order("兔各20")
        output = format_result(r)
        assert "04,16,28,40" in output
        assert "20" in output
        # total 保留在 ParseResult 中，输出不再显示总计行
        assert r.total == 80.0

    def test_error_format(self) -> None:
        r = parse_order("各20")
        output = format_result(r)
        assert "[错误]" in output

    def test_multi_zodiac_format(self) -> None:
        r = parse_order("兔龙蛇各10")
        output = format_result(r)
        # 输出不再包含总计行，但 total 保留在 ParseResult 中
        assert "总计" not in output
        assert r.total > 0


# ======================================================================
# 每 / 每注 替换「各」
# ======================================================================


class TestMeiAsSeparator:
    def test_mei_as_ge(self) -> None:
        r = parse_order("兔每10")
        assert r.success
        assert r.category == "兔"
        assert r.amount == 10.0

    def test_meizhu_as_ge(self) -> None:
        r = parse_order("红波每注20")
        assert r.success
        assert r.category == "红波"
        assert r.amount == 20.0


# ======================================================================
# 金额倍数 *N
# ======================================================================


class TestAmountMultiplier:
    def test_multiply_amount(self) -> None:
        r = parse_order("兔各10*3")
        assert r.success
        assert r.amount == 30.0
        assert r.total == 30.0 * 4  # 兔 4 号 × 30

    def test_multiply_with_space(self) -> None:
        r = parse_order("兔各10 * 5")
        assert r.success
        assert r.amount == 50.0


# ======================================================================
# 省略「各」的快捷格式
# ======================================================================


class TestNoSepShorthand:
    def test_zodiac_no_sep(self) -> None:
        r = parse_order("兔10")
        assert r.success
        assert r.category == "兔"
        assert r.amount == 10.0

    def test_number_list_no_sep(self) -> None:
        r = parse_order("01,02,03 30")
        assert r.success
        assert r.category == "纯数字"
        assert r.numbers == (1, 2, 3)
        assert r.total == 90.0


# ======================================================================
# 一行多单
# ======================================================================


class TestInlineMultiOrder:
    def test_comma_split_two_orders(self) -> None:
        results = parse_lines("兔各10，马各20")
        assert len(results) == 2
        assert results[0].category == "兔"
        assert results[1].category == "马"

    def test_comma_between_numbers_not_split(self) -> None:
        """数字间的逗号不应拆分。"""
        results = parse_lines("01,02,03各10")
        assert len(results) == 1


# ======================================================================
# 投注类型前缀
# ======================================================================


class TestBetTypePrefix:
    def test_pingma(self) -> None:
        r = parse_order("平码01,02,03各10")
        assert r.success
        assert r.category == "平码"
        assert r.numbers == (1, 2, 3)

    def test_pingte_yixiao(self) -> None:
        r = parse_order("平特一肖兔各10")
        assert r.success
        assert r.category == "平特一肖"
        assert r.numbers == (4, 16, 28, 40)
        assert r.total == 10

    def test_pingte_yiwei(self) -> None:
        r = parse_order("平特一尾1各10")
        assert r.success
        assert r.category == "平特一尾"
        assert 1 in r.numbers and 11 in r.numbers

    def test_buzhong_range(self) -> None:
        r = parse_order("不中5-24各2")
        assert r.success
        assert r.category == "N不中"
        assert len(r.numbers) == 20  # 5..24
        assert r.numbers[0] == 5
        assert r.numbers[-1] == 24
        assert r.total == 2

    @pytest.mark.parametrize(
        "text",
        [
            "N不中 08,09,10 各100",
            "不中 08,09,10 各100",
            "5不中 08,09,10,11,12 各100",
            "六不中 08,09,10,11,12,13 各100",
        ],
    )
    def test_non_hit_group_amount_is_not_multiplied(self, text: str) -> None:
        r = parse_order(text)
        assert r.success
        assert r.category == "N不中"
        assert r.amount == 100
        assert r.total == 100

    def test_non_hit_rejects_invalid_number(self) -> None:
        r = parse_order("N不中 08,50 各100")
        assert not r.success
        assert "无法解析N不中号码列表" in r.error

    def test_non_hit_deduplicates_numbers_with_group_amount(self) -> None:
        r = parse_order("N不中 08,09,08 各100")
        assert r.success
        assert r.numbers == (8, 9)
        assert r.total == 100


class TestRecordWindowAdvancedParseOptions:
    @pytest.mark.parametrize(
        ("text", "category", "total", "numbers_count"),
        [
            ("01各10", "纯数字", 10, 1),
            ("01,02,03各10", "纯数字", 30, 3),
            ("马各10", "马", 50, 5),
            ("羊马各10", "多生肖", 90, 9),
            ("红波各10", "红波", 170, 17),
            ("红单各10", "红单", 80, 8),
            ("大各10", "大", 250, 25),
            ("单各10", "单", 250, 25),
        ],
    )
    def test_real_samples_keep_default_parse_behavior(
        self,
        text: str,
        category: str,
        total: int,
        numbers_count: int,
    ) -> None:
        r = parse_order(text)
        assert r.success
        assert r.category == category
        assert r.total == total
        assert len(r.numbers) == numbers_count

    @pytest.mark.parametrize(
        ("text", "expected_zodiacs", "total"),
        [
            ("羊马各10", ["羊", "马"], 20),
            ("鼠牛虎各5", ["鼠", "牛", "虎"], 15),
            ("鼠、牛、虎各5", ["鼠", "牛", "虎"], 15),
        ],
    )
    def test_zodiac_each_real_samples_count_zodiac_groups(
        self,
        text: str,
        expected_zodiacs: list[str],
        total: int,
    ) -> None:
        r = parse_order(text, zodiac_each_mode=True)
        assert r.success
        assert r.category == "平特一肖"
        assert [name for name, _ in r.zodiac_groups] == expected_zodiacs
        assert r.total == total

    @pytest.mark.parametrize(
        ("text", "category", "total"),
        [
            ("01,02各10", "纯数字", 20),
            ("红波各10", "红波", 170),
        ],
    )
    def test_zodiac_each_real_samples_do_not_affect_non_zodiac(
        self,
        text: str,
        category: str,
        total: int,
    ) -> None:
        r = parse_order(text, zodiac_each_mode=True)
        assert r.success
        assert r.category == category
        assert r.total == total

    @pytest.mark.parametrize(
        ("text", "expected_zodiacs", "total"),
        [
            ("马10", ["马"], 10),
            ("马蛇10", ["马", "蛇"], 20),
            ("龙-羊-猴各80", ["龙", "羊", "猴"], 240),
        ],
    )
    def test_special_zodiac_mode_real_samples_count_zodiac_groups(
        self,
        text: str,
        expected_zodiacs: list[str],
        total: int,
    ) -> None:
        r = parse_order(text, special_zodiac_mode=True)
        assert r.success
        assert r.category == "平特一肖"
        assert [name for name, _ in r.zodiac_groups] == expected_zodiacs
        assert r.total == total

    @pytest.mark.parametrize(
        ("text", "category", "total"),
        [
            ("01各10", "纯数字", 10),
            ("红波各10", "红波", 170),
        ],
    )
    def test_special_zodiac_mode_real_samples_do_not_affect_non_zodiac(
        self,
        text: str,
        category: str,
        total: int,
    ) -> None:
        r = parse_order(text, special_zodiac_mode=True)
        assert r.success
        assert r.category == category
        assert r.total == total

    @pytest.mark.parametrize(
        ("text", "numbers", "total"),
        [
            ("25岁各10", (25,), 10),
            ("08岁各10", (8,), 10),
            ("1岁各10", (1,), 10),
            ("25岁、08岁各10", (8, 25), 20),
        ],
    )
    def test_age_writing_real_samples_normalize_numbers(
        self,
        text: str,
        numbers: tuple[int, ...],
        total: int,
    ) -> None:
        r = parse_order(text, age_writing=True)
        assert r.success
        assert r.category == "纯数字"
        assert r.numbers == numbers
        assert r.total == total

    @pytest.mark.parametrize("text", ["50岁各10", "00岁各10"])
    def test_age_writing_real_samples_reject_invalid_numbers(self, text: str) -> None:
        r = parse_order(text, age_writing=True)
        assert not r.success
        assert "岁写法号码" in r.error

    @pytest.mark.parametrize(
        ("text", "category", "total", "zodiacs", "numbers"),
        [
            ("25岁、08岁各10", "纯数字", 20, [], (8, 25)),
            ("羊马各10", "平特一肖", 20, ["羊", "马"], ()),
            ("马蛇10", "平特一肖", 20, ["马", "蛇"], ()),
            ("01各10", "纯数字", 10, [], (1,)),
        ],
    )
    def test_all_advanced_switches_real_samples_are_stable(
        self,
        text: str,
        category: str,
        total: int,
        zodiacs: list[str],
        numbers: tuple[int, ...],
    ) -> None:
        r = parse_order(
            text,
            age_writing=True,
            zodiac_each_mode=True,
            special_zodiac_mode=True,
        )
        assert r.success
        assert r.category == category
        assert r.total == total
        if zodiacs:
            assert [name for name, _ in r.zodiac_groups] == zodiacs
        if numbers:
            assert r.numbers == numbers

    def test_age_writing_normalizes_number_tokens(self) -> None:
        r = parse_order("25岁、08岁各10", age_writing=True)
        assert r.success
        assert r.category == "纯数字"
        assert r.numbers == (8, 25)
        assert r.total == 20

    def test_age_writing_rejects_invalid_number(self) -> None:
        r = parse_order("50岁各10", age_writing=True)
        assert not r.success
        assert "岁写法号码 50 超出范围" in r.error

    def test_age_writing_disabled_does_not_silently_parse(self) -> None:
        r = parse_order("25岁各10")
        assert not r.success
        assert "无法识别的类别" in r.error

    def test_normal_zodiac_expands_by_zodiac_numbers(self) -> None:
        r = parse_order("羊马各10")
        assert r.success
        assert r.category == "多生肖"
        assert len(r.numbers) == 9
        assert r.total == 90

    def test_zodiac_each_mode_counts_zodiac_groups(self) -> None:
        r = parse_order("羊马各10", zodiac_each_mode=True)
        assert r.success
        assert r.category == "平特一肖"
        assert [name for name, _ in r.zodiac_groups] == ["羊", "马"]
        assert r.total == 20

    def test_special_zodiac_mode_counts_single_zodiac(self) -> None:
        r = parse_order("马10", special_zodiac_mode=True)
        assert r.success
        assert r.category == "平特一肖"
        assert [name for name, _ in r.zodiac_groups] == ["马"]
        assert r.total == 10

    def test_special_zodiac_mode_counts_multiple_zodiacs(self) -> None:
        r = parse_order("马蛇10", special_zodiac_mode=True)
        assert r.success
        assert r.category == "平特一肖"
        assert [name for name, _ in r.zodiac_groups] == ["马", "蛇"]
        assert r.total == 20

    def test_special_zodiac_mode_does_not_affect_numbers(self) -> None:
        r = parse_order("01,02各10", special_zodiac_mode=True)
        assert r.success
        assert r.category == "纯数字"
        assert r.numbers == (1, 2)
        assert r.total == 20

    def test_zodiac_each_mode_does_not_affect_number_each(self) -> None:
        r = parse_order("01,02各10", zodiac_each_mode=True)
        assert r.success
        assert r.category == "纯数字"
        assert r.total == 20

    def test_all_advanced_options_are_stable_together(self) -> None:
        r = parse_order("1岁各10", age_writing=True, zodiac_each_mode=True, special_zodiac_mode=True)
        assert r.success
        assert r.category == "纯数字"
        assert r.numbers == (1,)
        assert r.total == 10

    def test_buzhong_zhi(self) -> None:
        """「至」也是合法范围分隔符。"""
        r = parse_order("不中10至20各2")
        assert r.success
        assert r.category == "N不中"
        assert r.numbers[0] == 10
        assert r.total == 2

    def test_lianwei(self) -> None:
        r = parse_order("连尾1,2,3各10")
        assert r.success
        assert r.category == "连尾"
        # 尾1: 1,11,21,31,41; 尾2: 2,12,22,32,42; 尾3: 3,13,23,33,43
        assert 1 in r.numbers and 11 in r.numbers and 41 in r.numbers
        assert 2 in r.numbers and 42 in r.numbers

    def test_dan_keyword(self) -> None:
        r = parse_order("胆马拖兔各10")
        assert r.success
        assert "肖" in r.category  # 胆肖 或 连肖
        assert 1 in r.numbers  # 马
        assert 4 in r.numbers  # 兔


# ======================================================================
# 排除号码: 不要 / 除 / 去掉 / 排除 / 除了
# ======================================================================


class TestExcludeNumbers:
    def test_buyao_single(self) -> None:
        r = parse_order("兔各30 不要04")
        assert r.success
        assert 4 not in r.numbers
        assert 16 in r.numbers
        assert len(r.numbers) == 3  # 4号→3号
        assert r.total == 30.0 * 3

    def test_chu_multiple(self) -> None:
        r = parse_order("兔各30 除04,16")
        assert r.success
        assert 4 not in r.numbers
        assert 16 not in r.numbers
        assert len(r.numbers) == 2
        assert r.total == 30.0 * 2

    def test_qudiao(self) -> None:
        r = parse_order("大各10 去掉25,26")
        assert r.success
        assert 25 not in r.numbers
        assert 26 not in r.numbers
        assert r.category == "大"

    def test_paichu(self) -> None:
        r = parse_order("红波各10 排除01")
        assert r.success
        assert 1 not in r.numbers
        assert r.category == "红波"

    def test_chule(self) -> None:
        r = parse_order("01,02,03,04各10 除了04")
        assert r.success
        assert r.numbers == (1, 2, 3)
        assert r.total == 30.0

    def test_no_exclusion_no_effect(self) -> None:
        r = parse_order("兔各30")
        assert r.success
        assert len(r.numbers) == 4

    def test_exclude_all_numbers(self) -> None:
        r = parse_order("兔各30 不要04,16,28,40")
        assert not r.success
        assert "无剩余" in r.error

    def test_exclude_with_marker_prefix(self) -> None:
        r = parse_order("张三 兔各30 不要04")
        assert r.success
        assert 4 not in r.numbers
