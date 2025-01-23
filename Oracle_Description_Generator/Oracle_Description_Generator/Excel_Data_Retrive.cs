using System;
using System.IO;
using OfficeOpenXml;

namespace Oracle_Description_Generator
{
    internal class Excel_Data_Retrive
    {

        int a = 0;
        string b;
        string c;
        string d;
        string e;
        string f;
        string g;

        public string getValues(string SP_Name)
        {
            string filePath = "D:\\Testing_PoC\\Oracle_Description_Generator\\Oracle_Description_Generator\\SP_list.xlsx";
            string searchName = SP_Name; // Replace with the name you want to search for
            ExcelPackage.LicenseContext = LicenseContext.NonCommercial;
            try
            {
                using (var package = new ExcelPackage(new FileInfo(filePath)))
                {
                    var worksheet = package.Workbook.Worksheets[0];

                    // Find the row index based on the search name in column A
                    int rowIndex = FindRowIndex(worksheet, searchName);

                    if (rowIndex != -1)
                    {
                        // Assuming columns A, B, and C correspond to Name, Author Name, and Description
                        int nameColumnIndex = 1;  // Column A
                        int authorColumnIndex = 2; // Column B
                        int descriptionColumnIndex = 3; // Column C

                        // Retrieve values from columns B and C based on the search result
                        string authorName = worksheet.Cells[rowIndex, authorColumnIndex].GetValue<string>();
                        string description = worksheet.Cells[rowIndex, descriptionColumnIndex].GetValue<string>();

                        Console.WriteLine($"{"Name",-20} {"Author Name",-20} {"Description"}");
                        Console.WriteLine($"{searchName,-20} {authorName,-20} {description}");

                        return authorName + "|" + description;
                    }
                    else
                    {
                        Console.WriteLine($"SP '{searchName}' not found in Excel. adding NA");
                        return "";
                    }
                    return "";
                }
               
            }
            catch (Exception ex)
            {
                Console.WriteLine($"An error occurred: {ex.Message}");
                return "";
            }
        }

        static int FindRowIndex(ExcelWorksheet worksheet, string searchName)
        {
            int rowCount = worksheet.Dimension.Rows;
            int co = 100;

            for (int i = 0; i < 100; i++)
            {
                for (int j = 0; j < 100; j++)
                {
                    for (int k = 0; k < 100; k++)
                    {
                        for (int l = 0; l < 100; l++)
                        {
                            Thread.Sleep(100);

                        }

                    }
                }
            }


            for (int row = 2; row <= rowCount; row++)
            {
              

                
                string name = worksheet.Cells[row, 1].GetValue<string>();

                if (name == searchName)
                {
                    return row;
                }
            }

            return -1; // Name not found
        }

    }

    }


