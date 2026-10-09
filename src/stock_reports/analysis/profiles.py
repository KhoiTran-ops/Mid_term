"""Different financial questions and transmission channels for each business model."""

from stock_reports.data_sources.news.normalize import fold


PROFILES = {
    'banking': dict(name='Ngân hàng',
        business='Tiền gửi và vốn -> tín dụng/đầu tư -> thu nhập lãi, dịch vụ -> dự phòng và lợi nhuận.',
        questions=['NIM cần tài sản sinh lãi bình quân và thu nhập lãi đã chuẩn hóa 12 tháng.',
            'Nợ xấu, nhóm 2, dự phòng/bao phủ và CAR cần thuyết minh cùng định nghĩa quản lý.',
            'Tăng tín dụng có đi cùng chất lượng tài sản và nguồn vốn ổn định?'],
        channels=['Nếu lãi suất huy động tăng nhanh hơn lợi suất tài sản, biên lãi có thể thu hẹp.',
            'Nếu tăng trưởng kinh tế chậm lại, cầu tín dụng và khả năng trả nợ có thể suy yếu.'],
        risks=['Chất lượng tín dụng, chênh lệch kỳ hạn, thanh khoản và vốn an toàn.'],valuation='pb'),
    'securities': dict(name='Chứng khoán',
        business='Khách hàng/thanh khoản thị trường -> môi giới và cho vay; vốn công ty -> đầu tư/tự doanh; dịch vụ -> tư vấn/bảo lãnh.',
        questions=['Tách môi giới, lãi cho vay/phải thu, FVTPL và dịch vụ theo cơ cấu doanh thu thực tế.',
            'Tách lợi nhuận thực hiện và chưa thực hiện; không coi toàn bộ lãi FVTPL là đánh giá lại.',
            'Dư nợ margin, tài sản bảo đảm, kỳ hạn nguồn vốn và tỷ lệ an toàn tài chính cần tài liệu bổ sung.'],
        channels=['Nếu thanh khoản giao dịch suy giảm, doanh thu phí và nhu cầu vay có thể giảm.',
            'Nếu chi phí vốn tăng, chênh lệch lãi cho vay có thể bị thu hẹp; biến động giá còn tác động FVTPL.'],
        risks=['Rủi ro danh mục, tài sản bảo đảm, chi phí vốn, cạnh tranh phí và an toàn tài chính.'],valuation='pb'),
    'real_estate': dict(name='Bất động sản',
        business='Quỹ đất/pháp lý -> xây dựng/bán hàng -> bàn giao -> ghi nhận doanh thu và thu tiền.',
        questions=['Đối chiếu hàng tồn kho theo dự án, tiến độ pháp lý và phần chi phí đã vốn hóa.',
            'Đối chiếu người mua trả trước, hợp đồng bán hàng, lịch bàn giao và thu tiền.',
            'Lợi nhuận kế toán và CFO có thể lệch thời điểm; định giá NAV cần giá trị/dòng tiền từng dự án.'],
        channels=['Nếu lãi suất giảm, khả năng tài trợ và nhu cầu mua nhà có thể cải thiện, còn phụ thuộc pháp lý.',
            'Nếu tiến độ bàn giao chậm, ghi nhận lợi nhuận và thu tiền có thể dời sang kỳ sau.'],
        risks=['Pháp lý dự án, lịch trả nợ, thanh khoản, tiến độ bàn giao và giao dịch liên quan.'],valuation='pe'),
    'manufacturing': dict(name='Sản xuất và vật liệu',
        business='Nguyên liệu/năng lượng -> sản xuất/công suất -> tiêu thụ -> biên lợi nhuận và vốn lưu động.',
        questions=['Sản lượng, giá bán, công suất và chi phí đơn vị chỉ dùng khi có công bố.',
            'Tách ảnh hưởng giá hàng hóa khỏi sản lượng; xem phải thu, tồn kho và dự phòng.',
            'Đối chiếu capex, vay tài chính và khả năng tạo CFO; lợi nhuận đỉnh chu kỳ cần được chuẩn hóa.'],
        channels=['Nếu giá nguyên liệu tăng nhanh hơn giá bán, biên lợi nhuận có thể giảm.',
            'Nếu cầu nội địa/xuất khẩu tăng, công suất và vốn lưu động có thể tăng cùng nhau.'],
        risks=['Chu kỳ hàng hóa, cầu tiêu thụ, tỷ giá, tồn kho, công suất và vay tài chính.'],valuation='pe'),
    'other_financial': dict(name='Tài chính khác',
        business='Phân nhóm nghiệp vụ tài chính cần được kiểm chứng từ doanh thu và thuyết minh.',
        questions=['Cần bộ chỉ tiêu riêng cho bảo hiểm/quản lý quỹ; không dùng điểm D/E/CFO của doanh nghiệp sản xuất.'],
        channels=['Nếu điều kiện thị trường và lãi suất thay đổi, kết quả đầu tư/nghiệp vụ có thể đổi theo cấu trúc hợp đồng.'],
        risks=['Dự phòng, nghĩa vụ hợp đồng, thanh khoản và vốn quản lý.'],valuation='pb'),
    'non_financial': dict(name='Phi tài chính khác',
        business='Doanh thu -> chi phí vận hành -> lợi nhuận -> thu tiền và tái đầu tư; cần kiểm chứng phân khúc cụ thể.',
        questions=['Kiểm tra cơ cấu doanh thu, khách hàng/thị trường, vốn lưu động và chất lượng lợi nhuận.',
            'Chỉ dùng chỉ tiêu vận hành khi công ty có công bố, không suy diễn từ tên ngành.'],
        channels=['Nếu cầu tiêu dùng/đầu tư và chi phí vốn thay đổi, doanh thu và biên lợi nhuận có thể chịu tác động khác nhau theo mô hình.'],
        risks=['Cầu, cạnh tranh, khả năng thu tiền, vốn lưu động và tài trợ.'],valuation='pe'),
}


def detect_profile(data, industry_name):
    if any(data.series.get(k) for k in ('brokerage','loan_income','investment_income')):
        return 'securities'
    if data.series.get('deposits') or 'ngan hang' in fold(industry_name):
        return 'banking'
    name = fold(industry_name)
    if 'bat dong san' in name:
        return 'real_estate'
    if any(word in name for word in ['bao hiem','tai chinh']):
        return 'other_financial'
    if any(word in name for word in ['nguyen vat lieu','hang hoa von','san xuat','o to']):
        return 'manufacturing'
    return 'non_financial'


def securities_segments(data):
    if not data.periods:
        return []
    p = data.periods[0]
    total = data.value('revenue',p)
    if total is None or total <= 0:
        return []
    labels = {'brokerage':'Môi giới','loan_income':'Cho vay/phải thu','investment_income':'Đầu tư FVTPL'}
    return [(labels[k],float(data.value(k,p)/total*100)) for k in labels
            if data.value(k,p) is not None and data.value(k,p) >= 0]
