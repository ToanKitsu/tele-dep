# Package 
    python -m pip install -r requirements.txt

# Python version
    Sử dụng Python < 3.13

Chuẩn bị một tài khoản Twitter để test chức năng
Chuẩn bị một tài khoản Telegram, nên sử dụng account phụ
1. Vào và start bot @redactedsystemsbot
    - Có 30 ngày free trial
    - Thêm follow acc twitter

2. Vào https://my.telegram.org/ đăng nhập tài khoản
    - Tạo API development tools
    - Điền thông tin cần thiết vào file .env

3. Vào @BotFather Telegram để tạo 1 bot
    - Lấy bot token và điền vào .env

4. Tạo group bất kì trên Telegram
    - Add bot được tạo ở @BotFather vào, cấp quyền admin
    - Lấy ID group, điền vào .env
    - Add vào bao nhiêu group thì điền bấy nhiêu ID, ID group là số âm

# Flow chạy hiện tại
Full mode = Text + media
FX mode = chỉ link fxtwitter ( một dạng link nhúng để preview nội dung link )

Bot Redacted gửi tin nhắn cho người dùng -> Bot Scraper lắng nghe sự kiện bot Redacted gửi tin nhắn cho người dùng -> Đọc text để xác nhận action -> Gửi file đến các group chọn FX Mode trước -> Tải media + text > Reupload lên server Telegram -> Gửi cho nhiều group chọn Full mode


Bạn có thể upload project lên github và dùng https://gitingest.com/ để lấy toàn bộ code để feed vào LLMs để biết thêm thông tin và luồng chạy thực tế
