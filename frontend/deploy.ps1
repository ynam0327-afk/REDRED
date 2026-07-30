$KeyPath = "C:\Users\X1_Carbon\Downloads\mocac.pem"
$Ec2Host = "ec2-user@13.218.95.73"

Write-Host "1/3 빌드 중..."
npm run build
if ($LASTEXITCODE -ne 0) { Write-Host "빌드 실패, 중단합니다."; exit 1 }

Write-Host "2/3 서버로 업로드 중..."
scp -i $KeyPath -r dist "${Ec2Host}:~/dist-new"

Write-Host "3/3 서버에 적용 중..."
ssh -i $KeyPath $Ec2Host "sudo rm -rf /usr/share/nginx/html/* && sudo cp -r ~/dist-new/* /usr/share/nginx/html/ && sudo chmod -R 755 /usr/share/nginx/html && rm -rf ~/dist-new"

Write-Host "완료: http://13.218.95.73"